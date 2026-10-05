"""
MIA Self-Modification — action journal: log every tool call, back up before changes, undo them later.

Change records (per action):
  {"op": "created",  "path"}                 — path did not exist before
  {"op": "modified", "path", "backup"}       — previous content copied to backup
  {"op": "deleted",  "path", "trash"}        — moved to MIA's trash instead of being destroyed
  {"op": "moved",    "path", "from"}         — moved/renamed from `from` to `path`
"""

import json
import secrets
import shutil
import time
from pathlib import Path

from server.selfmod import paths
from server.selfmod.paths import trusted

MAX_RESULT_CHARS = 500
MAX_ARG_CHARS = 200
# Arguments whose content should never be persisted to the log (only their length).
SENSITIVE_ARGS = {("type_text", "text"), ("set_clipboard", "text")}


def _new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _remove(path: Path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


class Action:
    """One logged operation and the filesystem changes it made."""

    def __init__(self, tool: str, summary: str, reason: str = "", session_id: str = "default", approval_id=None):
        self.id = _new_id()
        self.tool = tool
        self.summary = summary
        self.reason = reason
        self.session_id = session_id
        self.approval_id = approval_id
        self.changes: list[dict] = []

    def _slot(self, root: Path, path: Path) -> Path:
        return root / self.id / str(len(self.changes)) / (path.name or "root")

    def snapshot(self, path):
        """Record the current state of `path` before it is changed."""
        path = Path(path).absolute()
        if path.exists():
            backup = self._slot(paths.BACKUPS_DIR, path)
            with trusted():
                _copy(path, backup)
            self.changes.append({"op": "modified", "path": str(path), "backup": str(backup)})
        else:
            self.changes.append({"op": "created", "path": str(path)})

    def trash(self, path):
        """Move `path` into MIA's trash (recoverable) instead of deleting it."""
        path = Path(path).absolute()
        dest = self._slot(paths.TRASH_DIR, path)
        with trusted():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
        self.changes.append({"op": "deleted", "path": str(path), "trash": str(dest)})

    def moved(self, src, dst):
        self.changes.append({"op": "moved", "path": str(Path(dst).absolute()), "from": str(Path(src).absolute())})


class Journal:
    """Append-only JSONL log of everything MIA's tools did, plus rollback."""

    def start(self, tool: str, summary: str, reason: str = "", session_id: str = "default", approval_id=None) -> Action:
        return Action(tool, summary, reason, session_id, approval_id)

    def finish(self, action: Action, result: str, status: str = "done"):
        self._append({
            "id": action.id,
            "time": time.time(),
            "tool": action.tool,
            "summary": action.summary,
            "reason": action.reason,
            "session_id": action.session_id,
            "approval_id": action.approval_id,
            "status": status,
            "result": str(result)[:MAX_RESULT_CHARS],
            "changes": action.changes,
        })

    def log_call(self, tool: str, args: dict, result: str, session_id: str = "default", status: str = "done"):
        """Log a tool call that changes no files (or was blocked)."""
        shown = {}
        for key, value in args.items():
            if (tool, key) in SENSITIVE_ARGS:
                shown[key] = f"<{len(str(value))} chars>"
            else:
                text = str(value)
                shown[key] = text if len(text) <= MAX_ARG_CHARS else text[:MAX_ARG_CHARS] + "…"
        action = Action(tool, f"{tool}({json.dumps(shown, ensure_ascii=False)})", session_id=session_id)
        self.finish(action, result, status)

    def _append(self, entry: dict):
        try:
            with trusted():
                paths.SELFMOD_DIR.mkdir(parents=True, exist_ok=True)
                with open(paths.ACTION_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"  ⚠️ Could not write action log: {e}")

    def entries(self) -> list[dict]:
        if not paths.ACTION_LOG.exists():
            return []
        entries = []
        with open(paths.ACTION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

    def recent(self, limit: int = 10, changes_only: bool = True) -> list[dict]:
        entries = self.entries()
        undone = {e["rolls_back"] for e in entries if e.get("rolls_back")}
        if changes_only:
            entries = [e for e in entries if e.get("changes")]
        result = []
        for entry in reversed(entries[-limit:]):
            entry["undone"] = entry["id"] in undone
            result.append(entry)
        return result

    def rollback(self, action_id: str, session_id: str = "default") -> tuple[str, list[str]]:
        """Undo a logged change. Returns (message, affected paths)."""
        entries = self.entries()
        entry = next((e for e in entries if e["id"] == action_id), None)
        if not entry:
            return f"❌ No change with id {action_id}.", []
        if not entry.get("changes"):
            return f"❌ Change {action_id} didn't modify any files, so there is nothing to undo.", []
        if any(e.get("rolls_back") == action_id for e in entries):
            return f"❌ Change {action_id} was already undone.", []

        undo = self.start("undo_change", f"Undo {action_id}: {entry['summary']}", session_id=session_id)
        errors, affected = [], []

        for change in reversed(entry["changes"]):
            path = Path(change["path"])
            if paths.is_protected(path) or ("from" in change and paths.is_protected(change["from"])):
                errors.append(f"skipped protected path {path}")
                continue
            try:
                if change["op"] == "created":
                    if path.exists():
                        undo.trash(path)
                elif change["op"] == "modified":
                    undo.snapshot(path)
                    _remove(path)
                    _copy(Path(change["backup"]), path)
                elif change["op"] == "deleted":
                    if path.exists():
                        undo.snapshot(path)
                        _remove(path)
                    else:
                        undo.changes.append({"op": "created", "path": str(path)})
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with trusted():  # moving out of data/self_mod/trash
                        shutil.move(change["trash"], str(path))
                elif change["op"] == "moved":
                    original = Path(change["from"])
                    if original.exists():
                        errors.append(f"can't move {path} back: {original} already exists")
                        continue
                    shutil.move(str(path), str(original))
                    undo.moved(path, original)
                affected.append(str(path))
            except Exception as e:
                errors.append(f"{change['op']} {path}: {e}")

        status = "failed" if errors and not affected else "done"
        message = f"↩️ Undid change {action_id} ({entry['summary']})." if affected else f"❌ Could not undo {action_id}."
        if errors:
            message += "\nProblems: " + "; ".join(errors)
        if undo.changes:
            message += f"\nThis undo is itself change `{undo.id}`."

        record = {
            "id": undo.id, "time": time.time(), "tool": "undo_change", "summary": undo.summary,
            "reason": "", "session_id": session_id, "approval_id": None, "status": status,
            "result": message[:MAX_RESULT_CHARS], "changes": undo.changes, "rolls_back": action_id,
        }
        self._append(record)
        return message, affected

    def purge_older_than(self, days: int = 30):
        """Permanently remove backups and trashed items older than `days`."""
        cutoff = time.time() - days * 86400
        with trusted():
            for root in (paths.BACKUPS_DIR, paths.TRASH_DIR, paths.STAGING_DIR):
                if not root.exists():
                    continue
                for item in root.iterdir():
                    try:
                        if item.stat().st_mtime < cutoff:
                            _remove(item)
                    except Exception as e:
                        print(f"  ⚠️ Could not purge {item}: {e}")


journal = Journal()

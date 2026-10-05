"""
MIA Self-Modification — the safety guard every tool call passes through.

Rules:
  • MIA's core (paths.PROTECTED_PATHS) can never be changed           → blocked
  • removing/replacing lines, deleting, overwriting, sending/posting   → needs the user's approval
  • everything else                                                    → runs, logged, backed up
Approval requests must carry a `reason` explaining what is removed/sent and why.
"""

import difflib
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from server.plugins import TOOL_REGISTRY
from server.selfmod import paths
from server.selfmod.approvals import approvals
from server.selfmod.journal import Action, journal

MAX_DIFF_LINES = 150
MAX_DIFF_FILE_BYTES = 2 * 1024 * 1024

_session = ContextVar("mia_tool_session", default="default")


def current_session() -> str:
    return _session.get()


@dataclass
class Decision:
    verdict: str                                  # "allow" | "approve" | "block" | "error"
    summary: str = ""                             # one line: log entry / approval title
    message: str = ""                             # returned to the model for block/error
    kind: str = ""                                # approval kind: edit | delete | overwrite | command | send
    details: dict = field(default_factory=dict)   # shown to the user on the approval card
    targets: list = field(default_factory=list)   # paths to back up before applying


def allow(summary, targets=()):
    return Decision("allow", summary=summary, targets=list(targets))


def approve(kind, summary, details, targets=()):
    return Decision("approve", summary=summary, kind=kind, details=details, targets=list(targets))


def block(message):
    return Decision("block", message=f"🚫 Blocked: {message}")


def error(message):
    return Decision("error", message=f"❌ {message}")


CORE_BLOCK = ("{path} is part of MIA's core, which is read-only. New abilities go in dynamic tools "
              "(save_dynamic_tool) or skills instead.")

CHECKS: dict[str, Callable[[dict], Decision]] = {}
APPLIERS: dict[str, Callable[[Callable, dict, Action], str]] = {}


def check(tool_name):
    def decorator(fn):
        CHECKS[tool_name] = fn
        return fn
    return decorator


def applier(tool_name):
    def decorator(fn):
        APPLIERS[tool_name] = fn
        return fn
    return decorator


# ── Entry points ─────────────────────────────────────────────

def run_tool(tool_name: str, func: Callable, args: dict, session_id: str = "default") -> str:
    token = _session.set(session_id)
    try:
        policy = CHECKS.get(tool_name)
        if policy is None:
            with paths.untrusted():
                result = func(**args)
            journal.log_call(tool_name, args, result, session_id)
            return result

        decision = policy(args)
        if decision.verdict in ("block", "error"):
            journal.log_call(tool_name, args, decision.message, session_id, status=decision.verdict)
            return decision.message

        if decision.verdict == "approve":
            if not str(args.get("reason", "")).strip():
                return ("❌ This action needs the user's approval, and approval requests must include `reason`. "
                        "Call the tool again with `reason` explaining what will be removed/deleted/sent, "
                        "what it currently does, and why it has to go.")
            request = approvals.create(tool_name, args, decision.kind, decision.summary, decision.details, session_id)
            journal.log_call(tool_name, args, f"waiting for approval {request['id']}", session_id, status="pending")
            return (f"⏸️ Waiting for the user's approval (request {request['id']}): {decision.summary}. "
                    "The user has been shown the details and will approve or reject it. Stop here: tell the "
                    "user in one sentence what you're waiting for. Do NOT retry, and do NOT try to achieve "
                    "the same result another way.")

        return _apply(tool_name, func, args, decision, session_id)
    finally:
        _session.reset(token)


def execute_approved(request: dict) -> str:
    """Run an approved request. Re-checks first, so the core boundary still holds."""
    tool_name = request["tool_name"]
    entry = TOOL_REGISTRY.get(tool_name)
    policy = CHECKS.get(tool_name)
    if not entry or not policy:
        return f"❌ Tool {tool_name} is no longer available."
    args = dict(request["args"])
    decision = policy(args)
    if decision.verdict in ("block", "error"):
        return decision.message
    token = _session.set(request["session_id"])
    try:
        return _apply(tool_name, entry["function"], args, decision, request["session_id"], request["id"])
    finally:
        _session.reset(token)


def _apply(tool_name, func, args, decision: Decision, session_id, approval_id=None) -> str:
    action = journal.start(tool_name, decision.summary, str(args.get("reason", "")), session_id, approval_id)
    try:
        for target in decision.targets:
            action.snapshot(target)
        with paths.untrusted():
            result = APPLIERS.get(tool_name, _call)(func, args, action)
        status = "failed" if str(result).startswith("❌") else "done"
    except Exception as e:
        result, status = f"❌ Tool error ({tool_name}): {e}", "failed"
    journal.finish(action, result, status)
    if status == "done" and action.changes:
        result = f"{result}\n↩️ Change id `{action.id}` (can be undone with undo_change)."
    return result


def _call(func, args, action):
    return func(**args)


# ── Helpers ──────────────────────────────────────────────────

def _abs(path_str) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(path_str or ""))))
    return path if path.is_absolute() else Path.cwd() / path


def _describe(path: Path) -> str:
    try:
        if path.is_dir():
            count = sum(1 for _ in path.rglob("*"))
            return f"folder with {count} item(s)"
        size = path.stat().st_size
        return f"file, {size:,} bytes"
    except OSError:
        return "unknown"


def _diff(path: Path, new_text: str) -> tuple[int, str]:
    """(number of removed lines, unified diff) for replacing `path` with `new_text`."""
    if path.stat().st_size > MAX_DIFF_FILE_BYTES:
        return 1, f"(file is too large to diff — {path.stat().st_size:,} bytes would be replaced)"
    old = path.read_text(encoding="utf-8", errors="replace").splitlines()
    new = str(new_text).splitlines()
    diff = list(difflib.unified_diff(old, new, f"{path.name} (current)", f"{path.name} (new)", lineterm="", n=2))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    text = "\n".join(diff[:MAX_DIFF_LINES])
    if len(diff) > MAX_DIFF_LINES:
        text += f"\n… ({len(diff) - MAX_DIFF_LINES} more diff lines)"
    return removed, text


# ── Files ────────────────────────────────────────────────────

@check("write_file")
def _check_write_file(args):
    path = _abs(args.get("file_path"))
    if paths.is_protected(path):
        return block(CORE_BLOCK.format(path=path))
    if paths.is_inside(path, paths.DYNAMIC_TOOLS_DIR):
        return block("dynamic tools must be changed with save_dynamic_tool so they are checked and tested.")
    if path.is_file():
        removed, diff = _diff(path, args.get("content", ""))
        if removed:
            return approve("edit", f"Remove/replace {removed} line(s) in {path}",
                           {"path": str(path), "removed_lines": removed, "diff": diff}, targets=[path])
    return allow(f"Write {path}", targets=[path])


@check("delete_file")
def _check_delete_file(args):
    path = _abs(args.get("file_path"))
    if paths.is_protected(path):
        return block(CORE_BLOCK.format(path=path))
    if paths.is_inside(path, paths.DYNAMIC_TOOLS_DIR):
        return block("use delete_dynamic_tool to remove a dynamic tool.")
    if not path.exists():
        return error(f"Not found: {path}")
    return approve("delete", f"Delete {path}", {"path": str(path), "what": _describe(path),
                   "backup": "moved to MIA's trash (restorable for 30 days)"})


@applier("delete_file")
def _apply_delete_file(func, args, action):
    path = _abs(args.get("file_path"))
    action.trash(path)
    return f"✅ Deleted {path} (moved to MIA's trash)."


@check("move_file")
def _check_move_file(args):
    src, dst = _abs(args.get("source")), _abs(args.get("destination"))
    for path in (src, dst):
        if paths.is_protected(path):
            return block(CORE_BLOCK.format(path=path))
        if paths.is_inside(path, paths.DYNAMIC_TOOLS_DIR):
            return block("dynamic tools can't be moved by hand.")
    if not src.exists():
        return error(f"Not found: {src}")
    final = dst / src.name if dst.is_dir() else dst
    if final.exists():
        return approve("overwrite", f"Move {src} → {final}, replacing the existing item",
                       {"source": str(src), "replaces": str(final), "what": _describe(final),
                        "backup": "the replaced item is backed up first"}, targets=[final])
    return allow(f"Move {src} → {final}")


@applier("move_file")
def _apply_move_file(func, args, action):
    src, dst = _abs(args.get("source")), _abs(args.get("destination"))
    final = dst / src.name if dst.is_dir() else dst
    result = func(**args)
    if not str(result).startswith("❌"):
        action.moved(src, final)
    return result


# ── Skills ───────────────────────────────────────────────────

@check("uninstall_skill")
def _check_uninstall_skill(args):
    folder = paths.SKILLS_DIR / str(args.get("skill_name", ""))
    if not folder.is_dir() or not paths.is_inside(folder, paths.SKILLS_DIR):
        return error(f"Skill '{args.get('skill_name')}' not found.")
    return approve("delete", f"Uninstall skill '{folder.name}'",
                   {"path": str(folder), "what": _describe(folder), "backup": "moved to MIA's trash"})


@applier("uninstall_skill")
def _apply_uninstall_skill(func, args, action):
    action.trash(paths.SKILLS_DIR / str(args["skill_name"]))
    return f"✅ Removed skill '{args['skill_name']}' (moved to MIA's trash)."


@check("install_skill_from_url")
def _check_install_skill(args):
    folder = paths.SKILLS_DIR / str(args.get("skill_name", ""))
    if not paths.is_inside(folder, paths.SKILLS_DIR) or folder == paths.SKILLS_DIR:
        return error("Invalid skill name.")
    if (folder / "SKILL.md").exists():
        return approve("overwrite", f"Replace existing skill '{folder.name}' with {args.get('url')}",
                       {"path": str(folder / "SKILL.md"), "backup": "current version is backed up first"},
                       targets=[folder])
    return allow(f"Install skill '{folder.name}' from {args.get('url')}", targets=[folder])


# ── Commands ─────────────────────────────────────────────────

_CMD = r"(?<![-\w.$]){}(?![-\w.])"
_DELETE_WORDS = ["remove-item", "ri", "rm", "rmdir", "rd", "del", "erase", "clear-content", "clear-recyclebin",
                 "format-volume", "format", "diskpart", "cipher"]
_OVERWRITE_WORDS = ["set-content", "out-file"]
_DESTRUCTIVE_RE = re.compile(
    "|".join(_CMD.format(re.escape(w)) for w in _DELETE_WORDS + _OVERWRITE_WORDS)
    + r"|\bgit\s+(clean|reset\s+--hard|checkout\s+--|restore|rm|push\s+(-f|--force))\b"
    + r"|(?<![>\d])>(?![>&])(?!\s*\$?null\b)(?!\s*nul\b)",   # `>` overwrite redirect (not >>, 2>&1, > $null)
    re.IGNORECASE,
)
_WRITE_WORDS = _DELETE_WORDS + _OVERWRITE_WORDS + [
    "move-item", "mi", "mv", "move", "rename-item", "rni", "ren", "copy-item", "cpi", "cp", "copy", "xcopy",
    "robocopy", "new-item", "ni", "add-content", "ac", "mklink", "icacls", "takeown", "attrib", "git", "sed",
]
_WRITE_RE = re.compile("|".join(_CMD.format(re.escape(w)) for w in _WRITE_WORDS) + r"|>", re.IGNORECASE)


def _any_sep(posix_path: str) -> str:
    return r"[\\/]".join(re.escape(part) for part in posix_path.split("/"))


def _core_ref_pattern() -> re.Pattern:
    """Matches a protected path written absolutely, or relative to the project root (e.g. `server\\agent`)."""
    parts = []
    for protected in paths.PROTECTED_PATHS:
        parts.append(_any_sep(protected.as_posix()) + r"(?![\w-])")
        relative = _any_sep(protected.relative_to(paths.PROJECT_ROOT).as_posix())
        parts.append(r"(?:^|(?<=[\s\"'=(,;])|(?<=\.[\\/]))" + relative + r"(?=[\\/\s\"';),]|$)")
    return re.compile("|".join(parts), re.IGNORECASE)


_CORE_REF_RE = _core_ref_pattern()


@check("execute_command")
def _check_execute_command(args):
    command = str(args.get("command", ""))
    if _CORE_REF_RE.search(command) and _WRITE_RE.search(command):
        return block("this command looks like it changes MIA's core files, which are read-only.")
    match = _DESTRUCTIVE_RE.search(command)
    if match:
        return approve("command", f"Run a command that can delete or overwrite data (`{match.group(0).strip()}`)",
                       {"command": command, "shell": args.get("shell", "powershell"),
                        "backup": "⚠️ not possible for commands — this can't be undone by MIA"})
    return allow(f"Run: {command[:120]}")


# ── Screen actions that publish or pay ───────────────────────

_IRREVERSIBLE_CLICK_RE = re.compile(
    r"\b(send|post|share|publish|submit|tweet|pay|purchase|buy|checkout|place order|transfer|delete|remove|unsubscribe)\b",
    re.IGNORECASE,
)


@check("visual_find_and_click")
def _check_visual_click(args):
    description = str(args.get("element_description", ""))
    match = _IRREVERSIBLE_CLICK_RE.search(description)
    if match:
        return approve("send", f"Click '{description}' (this can't be undone)",
                       {"click": description, "note": "MIA finds the button again on screen when you approve."})
    return allow(f"Click '{description}'")


# ── Scheduled tasks & heartbeat ──────────────────────────────

def _block_inside_automation(action: str):
    # Unattended runs read untrusted content (emails, web pages); they must not be able to
    # plant new automations that would then run with nobody watching.
    if current_session().startswith("auto-"):
        return block(f"scheduled runs and heartbeats can't {action}. Ask the user to do it from chat.")
    return None


@check("schedule_task")
def _check_schedule_task(args):
    return _block_inside_automation("create scheduled tasks") or allow(f"Schedule task '{args.get('name', '')}'")


@check("configure_heartbeat")
def _check_configure_heartbeat(args):
    return _block_inside_automation("change the heartbeat") or allow("Update heartbeat settings")


@check("pause_scheduled_task")
def _check_pause_scheduled_task(args):
    return _block_inside_automation("pause or resume tasks") or allow(f"Pause/resume task {args.get('task_id')}")


@check("delete_scheduled_task")
def _check_delete_scheduled_task(args):
    from server.services.scheduler import SchedulerError, describe_schedule, task_scheduler

    blocked = _block_inside_automation("delete tasks")
    if blocked:
        return blocked
    try:
        task = task_scheduler.get(str(args.get("task_id", "")))
    except SchedulerError as e:
        return error(str(e))
    return approve("delete", f"Delete scheduled task '{task['name']}'", {
        "task": task["id"],
        "schedule": describe_schedule(task["schedule"]),
        "does": (task["instructions"] or task["command"])[:300],
        "backup": "⚠️ can't be undone — pausing keeps it instead",
    })


# ── Dynamic tools ────────────────────────────────────────────

@check("save_dynamic_tool")
def _check_save_dynamic_tool(args):
    from server.selfmod import dynamic_tools

    name = str(args.get("tool_name", ""))
    code, test_code = str(args.get("code", "")), str(args.get("test_code", ""))
    problems = dynamic_tools.validate(name, code, test_code)
    if problems:
        return error("The code was rejected, nothing was saved. Fix these and try again:\n- " + "\n- ".join(problems))
    passed, output = dynamic_tools.run_tests(name, code, test_code)
    if not passed:
        return error(f"Tests failed, nothing was saved. Output:\n{output}")

    folder = dynamic_tools.tool_dir(name)
    existing = folder / "tool.py"
    if existing.is_file():
        removed, diff = _diff(existing, code)
        if removed:
            version = dynamic_tools.read_manifest(name).get("version", 1)
            return approve("edit", f"Update dynamic tool '{name}' v{version} → v{version + 1}, removing {removed} line(s)",
                           {"tool": name, "removed_lines": removed, "tests": "passed", "diff": diff}, targets=[folder])
    return allow(f"{'Update' if existing.is_file() else 'Create'} dynamic tool '{name}'", targets=[folder])


@check("delete_dynamic_tool")
def _check_delete_dynamic_tool(args):
    from server.selfmod import dynamic_tools

    name = str(args.get("tool_name", ""))
    folder = dynamic_tools.tool_dir(name)
    if not dynamic_tools.NAME_RE.match(name) or not folder.is_dir():
        return error(f"Dynamic tool '{name}' not found.")
    return approve("delete", f"Delete dynamic tool '{name}'",
                   {"tool": name, "provides": ", ".join(dynamic_tools.registered_tools(name)) or "nothing loaded",
                    "backup": "moved to MIA's trash"})


@applier("delete_dynamic_tool")
def _apply_delete_dynamic_tool(func, args, action):
    from server.selfmod import dynamic_tools

    name = str(args["tool_name"])
    dynamic_tools.unload(name)
    action.trash(dynamic_tools.tool_dir(name))
    return f"✅ Dynamic tool '{name}' removed (moved to MIA's trash)."

"""
MIA Self-Modification — approval queue for actions that remove, delete or send something.

Requests are created by the guard when a tool call needs the user's OK. They can only be
resolved from a user channel (web chat, Telegram) — there is deliberately no tool for it,
so the model can never approve its own request.
"""

import json
import secrets
import time

from server.selfmod import paths
from server.selfmod.paths import trusted

EXPIRY_SECONDS = 24 * 3600


class ApprovalManager:
    def __init__(self):
        self._requests: dict[str, dict] = self._load()
        self._new: list[dict] = []

    # ── Persistence ──────────────────────────────────────────

    def _load(self) -> dict:
        try:
            if paths.APPROVALS_FILE.exists():
                return json.loads(paths.APPROVALS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠️ Could not load approvals: {e}")
        return {}

    def _save(self):
        # Keep only the most recent 200 resolved requests on disk.
        items = sorted(self._requests.values(), key=lambda r: r["created_at"])
        resolved = [r for r in items if r["status"] != "pending"]
        drop = {r["id"] for r in resolved[:-200]}
        self._requests = {r["id"]: r for r in items if r["id"] not in drop}
        try:
            with trusted():
                paths.SELFMOD_DIR.mkdir(parents=True, exist_ok=True)
                paths.APPROVALS_FILE.write_text(json.dumps(self._requests, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️ Could not save approvals: {e}")

    # ── Requests ─────────────────────────────────────────────

    def create(self, tool_name: str, args: dict, kind: str, title: str, details: dict, session_id: str) -> dict:
        request = {
            "id": secrets.token_hex(3),
            "tool_name": tool_name,
            "args": args,
            "kind": kind,
            "title": title,
            "details": details,
            "reason": str(args.get("reason", "")).strip(),
            "session_id": session_id,
            "status": "pending",
            "created_at": time.time(),
            "resolved_at": None,
            "resolved_via": None,
            "result": None,
        }
        self._requests[request["id"]] = request
        self._save()
        self._new.append(request)
        return request

    def drain_new(self) -> list[dict]:
        """Requests created since the last call — the agent loop forwards these to the user's channel."""
        new, self._new = self._new, []
        return new

    def _expire(self):
        now = time.time()
        changed = False
        for request in self._requests.values():
            if request["status"] == "pending" and now - request["created_at"] > EXPIRY_SECONDS:
                request["status"] = "expired"
                changed = True
        if changed:
            self._save()

    def pending(self) -> list[dict]:
        self._expire()
        return sorted((r for r in self._requests.values() if r["status"] == "pending"), key=lambda r: r["created_at"])

    def resolve(self, request_id: str, approved: bool, via: str) -> dict:
        """Approve or reject a request. Returns {"request", "result", "handled_now"}."""
        self._expire()
        request = self._requests.get(request_id)
        if not request:
            return {"request": None, "result": f"❌ No approval request with id {request_id}.", "handled_now": False}
        if request["status"] != "pending":
            return {"request": request, "result": f"This request is already {request['status']}.", "handled_now": False}

        request["resolved_at"] = time.time()
        request["resolved_via"] = via
        if not approved:
            request["status"] = "rejected"
            request["result"] = "Rejected — nothing was changed."
            self._save()
            return {"request": request, "result": request["result"], "handled_now": True}

        request["status"] = "approved"
        self._save()

        from server.selfmod.guard import execute_approved
        try:
            result = execute_approved(request)
        except Exception as e:
            result = f"❌ Failed to run approved action: {e}"
        request["status"] = "failed" if result.startswith(("❌", "🚫")) else "done"
        request["result"] = result[:2000]
        self._save()
        return {"request": request, "result": result, "handled_now": True}

    # ── Presentation ─────────────────────────────────────────

    @staticmethod
    def public(request: dict) -> dict:
        """What user channels get to see (full tool args can be huge, e.g. whole files)."""
        return {k: request[k] for k in (
            "id", "tool_name", "kind", "title", "details", "reason", "status", "created_at", "result",
        )}

    @staticmethod
    def followup_message(request: dict) -> str:
        """The message fed back to the agent so it can continue after the user decides."""
        header = "[Approval update from MIA's approval system — not typed by the user]\n"
        if request["status"] == "rejected":
            return (
                f"{header}The user REJECTED request {request['id']} ({request['title']}). Nothing was changed. "
                "Do not try to do the same thing another way. Briefly acknowledge it and, if the task can't "
                "continue without it, ask the user how they'd like to proceed."
            )
        return (
            f"{header}The user APPROVED request {request['id']} ({request['title']}).\n"
            f"Result: {request.get('result')}\n"
            "Continue the original task if anything is left; otherwise briefly confirm it's done."
        )

    @staticmethod
    def format_text(request: dict, limit: int = 3800) -> str:
        """Plain-text rendering for channels without rich UI (Telegram)."""
        lines = [f"⚠️ MIA needs your approval (#{request['id']})", request["title"], ""]
        if request.get("reason"):
            lines += [f"Why: {request['reason']}", ""]
        details = request.get("details") or {}
        for key, value in details.items():
            if key != "diff":
                lines.append(f"{key.replace('_', ' ').capitalize()}: {value}")
        if details.get("diff"):
            lines += ["", details["diff"]]
        text = "\n".join(lines)
        return text if len(text) <= limit else text[:limit] + "\n… (truncated — open the web UI for the full diff)"


approvals = ApprovalManager()

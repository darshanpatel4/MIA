"""
MIA Self-Improvement tools — let MIA write, test and manage its own dynamic tools,
and review or undo the changes it has made.

Safety (code checks, tests, approvals, backups) is enforced by server.selfmod.guard,
which intercepts these calls before the function bodies below run.
"""

import time

from server.plugins import tool
from server.selfmod import dynamic_tools
from server.selfmod.journal import journal

WRITING_GUIDE = (
    "Rules for `code`: register each function with "
    "`from server.plugins import tool` and "
    "`@tool(name=..., description=..., parameters={param: {\"type\": \"string\", \"description\": ...}}, required=[...])`; "
    "give every parameter a type hint, write a docstring, and return a string (✅/❌ prefixed). "
    "Not allowed: subprocess/threading/asyncio/ctypes/importlib, eval/exec/getattr, os.remove/unlink/rmtree "
    "and similar deletions, importing other `server.*` modules. To run commands, delete files or use other tools, "
    "`from server.selfmod.api import call_tool` and call e.g. call_tool(\"execute_command\", command=...) — those "
    "calls get the normal safety checks. "
    "Rules for `test_code`: `import tool` (or `from tool import ...`) and test with plain asserts or `test_*` "
    "functions. Tests must not have real side effects — no clicking, typing, sending, network calls or "
    "call_tool; test the pure logic (parsing, filtering, formatting) and pass fake data in."
)


@tool(
    name="save_dynamic_tool",
    description=(
        "Create or update one of MIA's own dynamic tools, when no existing tool or skill can do what the user "
        "needs. The code is checked, its tests run in a separate process, and it is loaded immediately. "
        "Updates that remove or replace existing lines need the user's approval. " + WRITING_GUIDE
    ),
    parameters={
        "tool_name": {"type": "string", "description": "Folder name for the tool: lowercase letters, digits, underscores (e.g. 'gmail_triage')"},
        "code": {"type": "string", "description": "Full contents of tool.py"},
        "test_code": {"type": "string", "description": "Full contents of test_tool.py"},
        "description": {"type": "string", "description": "One sentence: what this tool lets MIA do"},
        "reason": {"type": "string", "description": "Why this tool is needed. When updating and removing lines: what the removed code did and why it has to change."},
    },
    required=["tool_name", "code", "test_code", "description", "reason"],
)
def save_dynamic_tool(tool_name: str, code: str, test_code: str, description: str, reason: str) -> str:
    """Install a dynamic tool (already validated and tested by the guard)."""
    return dynamic_tools.install(tool_name, code, test_code, description, reason)


@tool(
    name="list_dynamic_tools",
    description="List the dynamic tools MIA has written for itself, with versions and the functions they provide.",
    parameters={},
)
def list_dynamic_tools() -> str:
    """List installed dynamic tools."""
    names = dynamic_tools.installed_names()
    if not names:
        return "No dynamic tools yet."
    lines = []
    for name in names:
        manifest = dynamic_tools.read_manifest(name)
        provides = ", ".join(dynamic_tools.registered_tools(name)) or "⚠️ not loaded"
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(manifest.get("updated_at", 0)))
        lines.append(f"- **{name}** v{manifest.get('version', '?')} — {manifest.get('description', '')} "
                     f"(provides: {provides}; updated {updated})")
    return "Dynamic tools:\n" + "\n".join(lines)


@tool(
    name="read_dynamic_tool",
    description="Read the source code and tests of one of MIA's dynamic tools (do this before updating it).",
    parameters={"tool_name": {"type": "string", "description": "Name of the dynamic tool"}},
    required=["tool_name"],
)
def read_dynamic_tool(tool_name: str) -> str:
    """Return tool.py and test_tool.py of a dynamic tool."""
    folder = dynamic_tools.tool_dir(tool_name)
    if not dynamic_tools.NAME_RE.match(tool_name) or not (folder / "tool.py").is_file():
        return f"❌ Dynamic tool '{tool_name}' not found."
    manifest = dynamic_tools.read_manifest(tool_name)
    code = (folder / "tool.py").read_text(encoding="utf-8")
    tests = (folder / "test_tool.py").read_text(encoding="utf-8") if (folder / "test_tool.py").exists() else ""
    return (f"🧩 {tool_name} v{manifest.get('version', '?')} — {manifest.get('description', '')}\n\n"
            f"tool.py:\n```python\n{code}\n```\n\ntest_tool.py:\n```python\n{tests}\n```")


@tool(
    name="delete_dynamic_tool",
    description="Remove one of MIA's dynamic tools. Needs the user's approval; the tool is moved to MIA's trash.",
    parameters={
        "tool_name": {"type": "string", "description": "Name of the dynamic tool"},
        "reason": {"type": "string", "description": "What the tool does and why it should be removed"},
    },
    required=["tool_name", "reason"],
)
def delete_dynamic_tool(tool_name: str, reason: str) -> str:
    """Handled by the guard's applier (unload + move to trash)."""
    return "❌ delete_dynamic_tool must run through the safety guard."


@tool(
    name="list_recent_changes",
    description="Show the most recent file changes MIA made (writes, deletions, tool updates) with their change ids, for review or undo.",
    parameters={"limit": {"type": "integer", "description": "How many changes to show. Default: 10", "default": 10}},
)
def list_recent_changes(limit: int = 10) -> str:
    """List recent logged changes."""
    entries = journal.recent(limit=int(limit))
    if not entries:
        return "No changes recorded yet."
    lines = []
    for entry in entries:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["time"]))
        flag = " (undone)" if entry.get("undone") else ""
        status = "" if entry["status"] == "done" else f" [{entry['status']}]"
        lines.append(f"- `{entry['id']}` {when} — {entry['summary']}{status}{flag}")
    return "Recent changes (newest first):\n" + "\n".join(lines)


@tool(
    name="undo_change",
    description="Undo a change MIA made, restoring files from backup or trash. Use only when the user asks to undo or roll back something. Find ids with list_recent_changes.",
    parameters={"change_id": {"type": "string", "description": "The change id, e.g. 20260916-142501-a1b2"}},
    required=["change_id"],
)
def undo_change(change_id: str) -> str:
    """Roll back a logged change and reload dynamic tools if any were affected."""
    from server.selfmod import paths
    from server.selfmod.guard import current_session

    message, affected = journal.rollback(change_id.strip(), current_session())
    if any(paths.is_inside(p, paths.DYNAMIC_TOOLS_DIR) for p in affected):
        dynamic_tools.reload_all()
        message += "\nDynamic tools reloaded."
    return message

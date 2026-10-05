"""
MIA Automation tools — let MIA schedule its own tasks from plain language and manage the heartbeat.

The model turns "every weekday at 8am" into a structured schedule; the tool validates it and
answers with the next run times so the model can confirm them back to the user.
"""

from server.plugins import tool
from server.services.scheduler import SchedulerError, describe_schedule, task_scheduler, upcoming_runs


def _schedule_from_args(cron: str, run_at: str, every_minutes: int) -> dict:
    given = [bool(cron), bool(run_at), bool(every_minutes)]
    if sum(given) != 1:
        raise SchedulerError("Give exactly one of: cron (repeating), run_at (one time) or every_minutes (interval).")
    if cron:
        return {"type": "cron", "cron": cron.strip()}
    if run_at:
        return {"type": "once", "run_at": run_at.strip()}
    return {"type": "interval", "every_minutes": int(every_minutes)}


def _channels(deliver_to: str) -> list:
    value = (deliver_to or "both").lower()
    return {"telegram": ["telegram"], "web": ["web"]}.get(value, ["telegram", "web"])


@tool(
    name="schedule_task",
    description=(
        "Schedule something for MIA to do later or repeatedly, described in plain language — e.g. 'Every weekday "
        "at 8am, check my email and send me a summary'. MIA runs the instructions at those times with all its "
        "tools and sends the result to the user. Convert the user's timing into exactly ONE of: `cron` "
        "(repeating; 5 fields 'minute hour day-of-month month day-of-week', day-of-week 0/7=Sun 1=Mon … 6=Sat, "
        "e.g. weekdays 8:00 = '0 8 * * 1-5'), `run_at` (one time, local ISO datetime like 2026-09-19T09:00), or "
        "`every_minutes`. Times are the PC's local time. Tell the user the upcoming run times this returns."
    ),
    parameters={
        "name": {"type": "string", "description": "Short name, e.g. 'Morning email summary'"},
        "instructions": {"type": "string", "description": "What to do each run, written as full instructions to yourself (what to check, what to include in the result)"},
        "cron": {"type": "string", "description": "Repeating schedule as a 5-field cron expression"},
        "run_at": {"type": "string", "description": "One-time run, local ISO datetime"},
        "every_minutes": {"type": "integer", "description": "Run every N minutes"},
        "deliver_to": {"type": "string", "description": "Where to send results: 'telegram', 'web' or 'both' (default)"},
    },
    required=["name", "instructions"],
)
def schedule_task(name: str, instructions: str, cron: str = "", run_at: str = "", every_minutes: int = 0,
                  deliver_to: str = "both") -> str:
    """Create an agent task on a schedule."""
    try:
        schedule = _schedule_from_args(cron, run_at, every_minutes)
        task = task_scheduler.add_task(name, "agent", schedule, instructions=instructions,
                                       deliver_to=_channels(deliver_to), created_by="mia")
        runs = upcoming_runs(schedule)
    except SchedulerError as e:
        return f"❌ {e}"
    return (f"✅ Scheduled '{task['name']}' (id {task['id']}, {describe_schedule(schedule)}), results to "
            f"{' + '.join(task['deliver_to'])}.\nNext runs: " + "; ".join(runs))


@tool(
    name="list_scheduled_tasks",
    description="List MIA's scheduled tasks with their schedule, next run, whether they're paused, and the last result.",
    parameters={},
)
def list_scheduled_tasks() -> str:
    """List scheduled tasks."""
    tasks = task_scheduler.list_tasks()
    if not tasks:
        return "No scheduled tasks."
    lines = []
    for t in tasks:
        state = "paused" if not t["enabled"] else t["status"]
        nxt = t["next_run"][:16].replace("T", " ") if t["next_run"] else "—"
        last = f"; last run {t['last_run'][:16].replace('T', ' ')}: {t['last_status']}" if t["last_run"] else ""
        what = t["instructions"] or f"command: {t['command']}"
        lines.append(f"- `{t['id']}` **{t['name']}** ({t['schedule_text']}, {state}, next {nxt}{last}) — {what[:120]}")
    return "Scheduled tasks:\n" + "\n".join(lines)


@tool(
    name="pause_scheduled_task",
    description="Pause or resume a scheduled task without deleting it.",
    parameters={
        "task_id": {"type": "string", "description": "Task id from list_scheduled_tasks"},
        "paused": {"type": "boolean", "description": "true to pause, false to resume"},
    },
    required=["task_id", "paused"],
)
def pause_scheduled_task(task_id: str, paused: bool) -> str:
    """Pause or resume a task."""
    try:
        task = task_scheduler.set_enabled(task_id, not paused)
    except SchedulerError as e:
        return f"❌ {e}"
    return f"✅ '{task['name']}' is now {'paused' if paused else 'active'}."


@tool(
    name="delete_scheduled_task",
    description="Delete a scheduled task permanently. Needs the user's approval; prefer pause_scheduled_task if they may want it back.",
    parameters={
        "task_id": {"type": "string", "description": "Task id from list_scheduled_tasks"},
        "reason": {"type": "string", "description": "Why it should be deleted"},
    },
    required=["task_id", "reason"],
)
def delete_scheduled_task(task_id: str, reason: str = "") -> str:
    """Delete a task (runs after approval)."""
    try:
        return "✅ " + task_scheduler.remove_task(task_id)["message"]
    except SchedulerError as e:
        return f"❌ {e}"


@tool(
    name="run_scheduled_task_now",
    description="Run a scheduled task right away (in the background); its result is delivered like a normal run.",
    parameters={"task_id": {"type": "string", "description": "Task id from list_scheduled_tasks"}},
    required=["task_id"],
)
def run_scheduled_task_now(task_id: str) -> str:
    """Trigger a task immediately."""
    try:
        task_scheduler.run_now(task_id)
    except SchedulerError as e:
        return f"❌ {e}"
    return "✅ Started. The result will be delivered when it finishes."


@tool(
    name="configure_heartbeat",
    description=(
        "Set up MIA's heartbeat: a periodic check that runs a checklist and only messages the user when something "
        "needs attention (e.g. urgent emails, low disk space, upcoming meetings). Pass `checklist` as the full list "
        "(one '- item' per line) to replace it; read the current one first with get_heartbeat."
    ),
    parameters={
        "enabled": {"type": "boolean", "description": "Turn the heartbeat on or off"},
        "every_minutes": {"type": "integer", "description": "How often to check (minimum 5, default 30)"},
        "active_hours": {"type": "string", "description": "Only check during these hours, e.g. '08:00-22:00' ('' = all day)"},
        "checklist": {"type": "string", "description": "The full checklist, one '- item' per line"},
        "deliver_to": {"type": "string", "description": "'telegram', 'web' or 'both'"},
    },
)
def configure_heartbeat(enabled: bool = None, every_minutes: int = None, active_hours: str = None,
                        checklist: str = None, deliver_to: str = None) -> str:
    """Update heartbeat settings."""
    try:
        status = task_scheduler.configure_heartbeat(
            enabled=enabled, every_minutes=every_minutes, active_hours=active_hours, checklist=checklist,
            deliver_to=_channels(deliver_to) if deliver_to else None)
    except SchedulerError as e:
        return f"❌ {e}"
    return get_heartbeat() if status else "❌ Could not update heartbeat."


@tool(
    name="get_heartbeat",
    description="Show the heartbeat's settings and current checklist.",
    parameters={},
)
def get_heartbeat() -> str:
    """Current heartbeat settings and checklist."""
    s = task_scheduler.heartbeat_status()
    state = "ON" if s["enabled"] else "OFF"
    warn = "" if s["has_items"] else "\n⚠️ The checklist has no items yet, so the heartbeat has nothing to check."
    return (f"Heartbeat {state}: every {s['every_minutes']} min, active {s['active_hours'] or 'all day'}, "
            f"alerts to {' + '.join(s['deliver_to'])}.{warn}\n\nChecklist (data/heartbeat.md):\n{s['checklist']}")

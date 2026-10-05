"""
MIA Scheduler — run MIA tasks (or shell commands) on a schedule, plus a proactive heartbeat.

Two kinds of scheduled task:
  • "agent"   — plain-language instructions MIA carries out, e.g. "check my email and summarize it"
  • "command" — a shell command (the original scheduler behaviour)

Results are delivered to the user's channels (Telegram and/or the web UI). The heartbeat
periodically runs a checklist (data/heartbeat.md) and only speaks up when something matters.

Tasks and heartbeat settings persist in data/automations.json, so they survive restarts.
Runs missed while MIA was off are not replayed (except within the grace period below).
"""

import asyncio
import json
import re
import secrets
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from server.config import config
from server.services.command_runner import command_runner

STORE_FILE = config.DATA_DIR / "automations.json"
HEARTBEAT_FILE = config.DATA_DIR / "heartbeat.md"
HEARTBEAT_JOB = "heartbeat"
HEARTBEAT_OK = "HEARTBEAT_OK"
MISFIRE_GRACE_SECONDS = 15 * 60
HISTORY_PER_TASK = 20
CHANNELS = ("telegram", "web")

DEFAULT_HEARTBEAT = {
    "enabled": False,
    "every_minutes": 30,
    "active_hours": "08:00-22:00",
    "deliver_to": ["telegram", "web"],
    "last_run": None,
    "last_alert": None,
}

HEARTBEAT_TEMPLATE = """# MIA heartbeat checklist
# MIA reads this every heartbeat and only messages you when something here needs attention.
# One item per line. Lines starting with # are ignored. Examples:
#
# - Check my inbox for unread emails from my manager or anything marked urgent
# - Warn me if disk space on C: drops below 10 GB
# - Remind me about calendar events starting in the next hour
"""

_DOW_NAMES = {"0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri", "6": "sat", "7": "sun"}


class SchedulerError(ValueError):
    pass


def _normalize_day_of_week(field: str) -> str:
    """Standard cron counts 0/7=Sunday, 1=Monday; APScheduler counts 0=Monday.
    Convert numbers to names so '1-5' means Monday-Friday as users expect."""
    def convert(token: str) -> str:
        step = ""
        if "/" in token:
            token, step = token.split("/", 1)
            step = "/" + step
        parts = token.split("-")
        if all(p.isdigit() for p in parts):
            parts = [_DOW_NAMES.get(p, p) for p in parts]
        return "-".join(parts) + step
    return ",".join(convert(t) for t in field.split(","))


def build_trigger(schedule: dict):
    """Validate a schedule dict and return an APScheduler trigger."""
    kind = schedule.get("type")
    try:
        if kind == "cron":
            fields = str(schedule.get("cron", "")).split()
            if len(fields) != 5:
                raise SchedulerError("cron needs 5 fields: minute hour day-of-month month day-of-week, e.g. '0 8 * * 1-5'")
            minute, hour, day, month, dow = fields
            return CronTrigger(minute=minute, hour=hour, day=day, month=month,
                               day_of_week=_normalize_day_of_week(dow))
        if kind == "once":
            run_at = datetime.fromisoformat(str(schedule.get("run_at", "")))
            if run_at <= datetime.now():
                raise SchedulerError(f"run_at {run_at:%Y-%m-%d %H:%M} is in the past")
            return DateTrigger(run_date=run_at)
        if kind == "interval":
            minutes = int(schedule.get("every_minutes", 0))
            if minutes < 1:
                raise SchedulerError("every_minutes must be at least 1")
            return IntervalTrigger(minutes=minutes)
    except SchedulerError:
        raise
    except (ValueError, TypeError) as e:
        raise SchedulerError(f"Invalid schedule: {e}")
    raise SchedulerError("schedule type must be 'cron', 'once' or 'interval'")


def describe_schedule(schedule: dict) -> str:
    kind = schedule.get("type")
    if kind == "cron":
        return f"cron {schedule['cron']}"
    if kind == "once":
        return f"once at {datetime.fromisoformat(schedule['run_at']):%Y-%m-%d %H:%M}"
    return f"every {schedule['every_minutes']} min"


def upcoming_runs(schedule: dict, count: int = 3) -> list[str]:
    trigger = build_trigger(schedule)
    runs, previous = [], None
    now = datetime.now().astimezone()
    for _ in range(count):
        nxt = trigger.get_next_fire_time(previous, previous or now)
        if not nxt:
            break
        runs.append(nxt.strftime("%a %d %b %Y %H:%M"))
        previous = nxt
    return runs


def _in_active_hours(active_hours: str) -> bool:
    if not active_hours:
        return True
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", active_hours)
    if not match:
        return True
    start = dtime(int(match[1]), int(match[2]))
    end = dtime(int(match[3]), int(match[4]))
    now = datetime.now().time()
    return start <= now <= end if start <= end else (now >= start or now <= end)  # handles overnight ranges


def heartbeat_checklist() -> str:
    """The active checklist lines from data/heartbeat.md (comments and blanks removed)."""
    if not HEARTBEAT_FILE.exists():
        return ""
    lines = [l.strip() for l in HEARTBEAT_FILE.read_text(encoding="utf-8").splitlines()]
    return "\n".join(l for l in lines if l and not l.startswith("#"))


class TaskScheduler:
    """Schedule MIA tasks and commands, deliver their results, and run the heartbeat."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "misfire_grace_time": MISFIRE_GRACE_SECONDS})
        self._tasks: dict[str, dict] = {}
        self.heartbeat: dict = dict(DEFAULT_HEARTBEAT)
        self._running: set[str] = set()
        self._load()

    # ── Lifecycle / persistence ──────────────────────────────

    def start(self):
        """Start the scheduler and register every saved task."""
        if self.scheduler.running:
            return
        self.scheduler.start()
        for task in self._tasks.values():
            self._register(task)
        self._register_heartbeat()
        print(f"  ✅ Task scheduler started ({len(self._tasks)} task(s), heartbeat {'on' if self.heartbeat['enabled'] else 'off'})")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _load(self):
        try:
            if STORE_FILE.exists():
                data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
                self._tasks = {t["id"]: t for t in data.get("tasks", [])}
                self.heartbeat = {**DEFAULT_HEARTBEAT, **data.get("heartbeat", {})}
        except Exception as e:
            print(f"  ⚠️ Could not load automations: {e}")
        if not HEARTBEAT_FILE.exists():
            try:
                HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
                HEARTBEAT_FILE.write_text(HEARTBEAT_TEMPLATE, encoding="utf-8")
            except Exception:
                pass

    def _save(self):
        try:
            STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STORE_FILE.write_text(json.dumps({"tasks": list(self._tasks.values()), "heartbeat": self.heartbeat},
                                             indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️ Could not save automations: {e}")

    def _register(self, task: dict):
        if self.scheduler.get_job(task["id"]):
            self.scheduler.remove_job(task["id"])
        if not task.get("enabled", True) or task.get("status") == "completed":
            return
        try:
            trigger = build_trigger(task["schedule"])
        except SchedulerError as e:
            if task["schedule"].get("type") == "once":  # a one-off that fired while MIA was off
                task["status"] = "missed"
                task["enabled"] = False
                self._save()
                return
            print(f"  ⚠️ Task {task['id']} has an invalid schedule: {e}")
            return
        self.scheduler.add_job(self._run_task, trigger=trigger, args=[task["id"]], id=task["id"], name=task["name"])

    def _next_run(self, task_id: str) -> Optional[str]:
        job = self.scheduler.get_job(task_id) if self.scheduler.running else None
        return job.next_run_time.isoformat() if job and job.next_run_time else None

    # ── Task management ──────────────────────────────────────

    def add_task(self, name: str, kind: str, schedule: dict, instructions: str = "", command: str = "",
                 deliver_to: Optional[list] = None, created_by: str = "user") -> dict:
        if kind not in ("agent", "command"):
            raise SchedulerError("kind must be 'agent' or 'command'")
        if kind == "agent" and not instructions.strip():
            raise SchedulerError("instructions are required for an agent task")
        if kind == "command" and not command.strip():
            raise SchedulerError("command is required for a command task")
        deliver_to = [c for c in (deliver_to or list(CHANNELS)) if c in CHANNELS] or ["web"]
        build_trigger(schedule)  # validate before saving

        task = {
            "id": "task_" + secrets.token_hex(3),
            "name": (name or instructions or command).strip()[:80],
            "kind": kind,
            "instructions": instructions.strip(),
            "command": command.strip(),
            "schedule": schedule,
            "deliver_to": deliver_to,
            "enabled": True,
            "status": "active",
            "created": datetime.now().isoformat(),
            "created_by": created_by,
            "last_run": None,
            "last_status": None,
            "last_result": None,
            "run_count": 0,
            "history": [],
        }
        self._tasks[task["id"]] = task
        self._save()
        if self.scheduler.running:
            self._register(task)
        return self.public(task)

    def get(self, task_id: str) -> dict:
        if task_id not in self._tasks:
            raise SchedulerError(f"No task with id {task_id}")
        return self._tasks[task_id]

    def set_enabled(self, task_id: str, enabled: bool) -> dict:
        task = self.get(task_id)
        task["enabled"] = enabled
        if enabled and task.get("status") in ("completed", "missed"):
            build_trigger(task["schedule"])  # a one-off can only be re-enabled if its time is still ahead
            task["status"] = "active"
        self._save()
        self._register(task)
        return self.public(task)

    def remove_task(self, task_id: str) -> dict:
        task = self.get(task_id)
        if self.scheduler.get_job(task_id):
            self.scheduler.remove_job(task_id)
        del self._tasks[task_id]
        self._save()
        return {"success": True, "message": f"Removed task '{task['name']}'"}

    def list_tasks(self) -> list:
        return [self.public(t) for t in sorted(self._tasks.values(), key=lambda t: t["created"])]

    def public(self, task: dict) -> dict:
        return {**task, "schedule_text": describe_schedule(task["schedule"]), "next_run": self._next_run(task["id"]),
                "running": task["id"] in self._running}

    def run_now(self, task_id: str):
        self.get(task_id)
        asyncio.get_running_loop().create_task(self._run_task(task_id, manual=True))

    # Backwards-compatible helpers used by the original /api/tasks endpoint (command tasks).
    def add_one_time_task(self, command: str, run_at: str, name: Optional[str] = None) -> dict:
        try:
            task = self.add_task(name, "command", {"type": "once", "run_at": run_at}, command=command, deliver_to=["web"])
            return {"success": True, "task_id": task["id"], "message": f"Scheduled '{task['name']}' for {run_at}"}
        except SchedulerError as e:
            return {"success": False, "error": str(e)}

    def add_recurring_task(self, command: str, cron_expression: str, name: Optional[str] = None) -> dict:
        try:
            task = self.add_task(name, "command", {"type": "cron", "cron": cron_expression}, command=command, deliver_to=["web"])
            return {"success": True, "task_id": task["id"], "message": f"Scheduled '{task['name']}' with cron: {cron_expression}"}
        except SchedulerError as e:
            return {"success": False, "error": str(e)}

    # ── Running tasks ────────────────────────────────────────

    async def _run_task(self, task_id: str, manual: bool = False):
        task = self._tasks.get(task_id)
        if not task or task_id in self._running:
            return
        self._running.add(task_id)
        started = datetime.now()
        print(f"  ⏰ Running scheduled task: {task['name']} ({task_id})")
        try:
            if task["kind"] == "command":
                result = await asyncio.to_thread(command_runner.execute_sync, task["command"])
                status = "done" if result["success"] else "failed"
                text = (result["stdout"] or result["stderr"] or f"exit code {result['exit_code']}").strip()[:3000]
                requests = []
            else:
                status, text, requests = await self._run_agent(
                    session_id=f"auto-{task_id}",
                    prompt=self._task_prompt(task),
                )
        except Exception as e:
            status, text, requests = "failed", f"❌ {e}", []

        task["last_run"] = started.isoformat()
        task["last_status"] = status
        task["last_result"] = text
        task["run_count"] = task.get("run_count", 0) + 1
        task["history"] = ([{"time": started.isoformat(), "status": status, "result": text[:1000], "manual": manual}]
                           + task.get("history", []))[:HISTORY_PER_TASK]
        if task["schedule"]["type"] == "once" and not manual:
            task["status"] = "completed"
            task["enabled"] = False
        self._running.discard(task_id)
        self._save()

        icon = "✅" if status == "done" else "⚠️"
        await deliver(task["deliver_to"], f"{icon} {task['name']}", text, requests)

    @staticmethod
    def _task_prompt(task: dict) -> str:
        previous = ""
        if task.get("last_result"):
            previous = f"\nYour result from the previous run ({task['last_run'][:16]}), for context:\n{task['last_result'][:1500]}\n"
        return (
            f"[Scheduled task '{task['name']}' — started automatically by MIA's scheduler at "
            f"{datetime.now():%A %d %B %Y %H:%M}. The user is not watching live.]\n"
            "Carry out the instructions below using your tools. Don't ask the user questions — make sensible "
            "choices and note any assumptions. Anything that needs approval will be sent to the user; don't "
            "work around it. Your final reply is sent to the user as the result, so make it a short, clear "
            "report (no preamble about being a scheduled task).\n"
            f"{previous}\nInstructions:\n{task['instructions']}"
        )

    async def _run_agent(self, session_id: str, prompt: str) -> tuple[str, str, list]:
        """Run MIA on a prompt in its own session. Returns (status, final text, approval requests)."""
        from server.agent.core import agent
        from server.agent.memory import memory

        memory.clear(session_id)  # each run starts clean; the previous result is passed in the prompt instead
        text, status, requests = "", "done", []
        async for event in agent.stream_chat(prompt, session_id):
            if event["type"] == "done":
                text = event["message"]
            elif event["type"] == "error":
                text, status = f"❌ {event['message']}", "failed"
            elif event["type"] == "approval_request":
                requests.append(event["request"])
        if requests and status == "done":
            status = "waiting_approval"
        return status, (text or "Done.").strip(), requests

    # ── Heartbeat ────────────────────────────────────────────

    def configure_heartbeat(self, enabled: Optional[bool] = None, every_minutes: Optional[int] = None,
                            active_hours: Optional[str] = None, deliver_to: Optional[list] = None,
                            checklist: Optional[str] = None) -> dict:
        if every_minutes is not None:
            if int(every_minutes) < 5:
                raise SchedulerError("every_minutes must be at least 5")
            self.heartbeat["every_minutes"] = int(every_minutes)
        if active_hours is not None:
            if active_hours and not re.fullmatch(r"\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\s*", active_hours):
                raise SchedulerError("active_hours must look like '08:00-22:00' (or empty for all day)")
            self.heartbeat["active_hours"] = active_hours.strip()
        if deliver_to is not None:
            self.heartbeat["deliver_to"] = [c for c in deliver_to if c in CHANNELS] or ["web"]
        if checklist is not None:
            HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT_FILE.write_text(checklist if checklist.strip() else HEARTBEAT_TEMPLATE, encoding="utf-8")
        if enabled is not None:
            self.heartbeat["enabled"] = bool(enabled)
        self._save()
        if self.scheduler.running:
            self._register_heartbeat()
        return self.heartbeat_status()

    def heartbeat_status(self) -> dict:
        job = self.scheduler.get_job(HEARTBEAT_JOB) if self.scheduler.running else None
        return {
            **self.heartbeat,
            "checklist": HEARTBEAT_FILE.read_text(encoding="utf-8") if HEARTBEAT_FILE.exists() else HEARTBEAT_TEMPLATE,
            "has_items": bool(heartbeat_checklist()),
            "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "running": HEARTBEAT_JOB in self._running,
        }

    def _register_heartbeat(self):
        if self.scheduler.get_job(HEARTBEAT_JOB):
            self.scheduler.remove_job(HEARTBEAT_JOB)
        if self.heartbeat["enabled"]:
            self.scheduler.add_job(self._run_heartbeat, IntervalTrigger(minutes=self.heartbeat["every_minutes"]),
                                   id=HEARTBEAT_JOB, name="Heartbeat")

    async def _run_heartbeat(self, manual: bool = False) -> dict:
        """Check the heartbeat list; deliver only if something needs attention."""
        checklist = heartbeat_checklist()
        if not checklist:
            return {"status": "skipped", "message": "The heartbeat checklist is empty."}
        if not manual and not _in_active_hours(self.heartbeat.get("active_hours", "")):
            return {"status": "skipped", "message": "Outside active hours."}
        if HEARTBEAT_JOB in self._running:
            return {"status": "skipped", "message": "A heartbeat is already running."}

        self._running.add(HEARTBEAT_JOB)
        try:
            last_alert = self.heartbeat.get("last_alert") or {}
            previous = (f"\nLast alert you sent ({last_alert.get('time', '')[:16]}) — don't repeat it unless something changed:\n"
                        f"{last_alert.get('text', '')[:1000]}\n") if last_alert else ""
            prompt = (
                f"[Heartbeat — MIA's periodic check at {datetime.now():%A %d %B %Y %H:%M}. The user is not watching live.]\n"
                "Go through the checklist below using your tools. Only report things that need the user's "
                f"attention now. If nothing does, reply with exactly {HEARTBEAT_OK} and nothing else. "
                "Otherwise reply with a short alert listing only what matters. Don't ask questions.\n"
                f"{previous}\nChecklist:\n{checklist}"
            )
            status, text, requests = await self._run_agent(session_id="auto-heartbeat", prompt=prompt)
        except Exception as e:
            status, text, requests = "failed", f"❌ {e}", []
        finally:
            self._running.discard(HEARTBEAT_JOB)

        now = datetime.now().isoformat()
        self.heartbeat["last_run"] = now
        quiet = status == "done" and text.strip().upper().startswith(HEARTBEAT_OK) and not requests
        if quiet:
            self._save()
            return {"status": "ok", "message": "Nothing needs your attention."}

        self.heartbeat["last_alert"] = {"time": now, "text": text[:2000]}
        self._save()
        await deliver(self.heartbeat["deliver_to"], "🔔 MIA heartbeat", text, requests)
        return {"status": "alert", "message": text}

    async def run_heartbeat_now(self) -> dict:
        return await self._run_heartbeat(manual=True)


# ── Delivery ─────────────────────────────────────────────────

async def deliver(channels: list, title: str, text: str, approval_requests: list = ()):
    """Send a result to the user's channels, including any approval requests it raised."""
    if "web" in channels:
        from server.services.notifications import notifications
        level = "warning" if title.startswith(("⚠️", "🔔")) else "success"
        await notifications.send(title, text[:500], level=level, data={"full_text": text})
        for request in approval_requests:
            await notifications.broadcast({"type": "approval_request", "request": request})
    if "telegram" in channels:
        from server.channels.telegram_bot import send_to_owner
        await send_to_owner(f"{title}\n\n{text}", approval_requests)


task_scheduler = TaskScheduler()

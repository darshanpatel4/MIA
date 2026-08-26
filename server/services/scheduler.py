"""
MIA Scheduler — Schedule commands and tasks to run at specific times.
"""

import json
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from server.services.command_runner import command_runner


class TaskScheduler:
    """Schedule and manage timed tasks."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._tasks: dict[str, dict] = {}
        self._task_counter = 0

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            print("  ✅ Task scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()

    def add_one_time_task(self, command: str, run_at: str, name: Optional[str] = None) -> dict:
        """Schedule a one-time task.

        Args:
            command: PowerShell command to run.
            run_at: ISO format datetime (e.g., '2024-01-15T14:30:00').
            name: Optional task name.
        """
        try:
            run_datetime = datetime.fromisoformat(run_at)
            self._task_counter += 1
            task_id = f"task_{self._task_counter}"
            task_name = name or f"Task {self._task_counter}"

            self.scheduler.add_job(
                self._execute_task,
                trigger=DateTrigger(run_date=run_datetime),
                args=[task_id, command],
                id=task_id,
                name=task_name,
            )

            self._tasks[task_id] = {
                "id": task_id,
                "name": task_name,
                "command": command,
                "type": "one_time",
                "scheduled_at": run_at,
                "status": "pending",
                "created": datetime.now().isoformat(),
            }

            return {"success": True, "task_id": task_id, "message": f"Scheduled '{task_name}' for {run_at}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_recurring_task(self, command: str, cron_expression: str, name: Optional[str] = None) -> dict:
        """Schedule a recurring task using cron expression.

        Args:
            command: PowerShell command to run.
            cron_expression: Cron expression (e.g., '*/5 * * * *' for every 5 minutes).
            name: Optional task name.
        """
        try:
            parts = cron_expression.strip().split()
            if len(parts) != 5:
                return {"success": False, "error": "Invalid cron expression. Use 5 fields: minute hour day month weekday"}

            self._task_counter += 1
            task_id = f"task_{self._task_counter}"
            task_name = name or f"Recurring Task {self._task_counter}"

            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4]
            )

            self.scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                args=[task_id, command],
                id=task_id,
                name=task_name,
            )

            self._tasks[task_id] = {
                "id": task_id,
                "name": task_name,
                "command": command,
                "type": "recurring",
                "cron": cron_expression,
                "status": "active",
                "created": datetime.now().isoformat(),
                "last_run": None,
                "run_count": 0,
            }

            return {"success": True, "task_id": task_id, "message": f"Scheduled '{task_name}' with cron: {cron_expression}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def remove_task(self, task_id: str) -> dict:
        """Remove a scheduled task."""
        try:
            self.scheduler.remove_job(task_id)
            if task_id in self._tasks:
                del self._tasks[task_id]
            return {"success": True, "message": f"Removed task {task_id}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tasks(self) -> list:
        """List all scheduled tasks."""
        return list(self._tasks.values())

    def _execute_task(self, task_id: str, command: str):
        """Execute a scheduled task."""
        print(f"  ⏰ Executing scheduled task: {task_id}")
        result = command_runner.execute_sync(command)

        if task_id in self._tasks:
            self._tasks[task_id]["last_run"] = datetime.now().isoformat()
            self._tasks[task_id]["last_result"] = {
                "success": result["success"],
                "exit_code": result["exit_code"],
                "output": result["stdout"][:500],
            }
            if self._tasks[task_id]["type"] == "one_time":
                self._tasks[task_id]["status"] = "completed"
            else:
                self._tasks[task_id]["run_count"] = self._tasks[task_id].get("run_count", 0) + 1


# Global instance
task_scheduler = TaskScheduler()

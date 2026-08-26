"""
MIA REST API Routes — Core HTTP endpoints.
"""

import os
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Query, Request
from fastapi.responses import FileResponse

from server.auth import require_auth
from server.agent.core import agent
from server.services.file_manager import file_manager
from server.services.screen import screen_streamer
from server.services.system_monitor import system_monitor
from server.services.process_manager import process_manager
from server.services.command_runner import command_runner
from server.services.scheduler import task_scheduler
from server.services.notifications import notifications
from server.services.error_logger import error_logger
from server.agent.memory import memory
from server.plugins.skills import get_skills_index
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api", tags=["api"])


# ── Request Models ───────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    
class RenameSessionRequest(BaseModel):
    new_name: str

class CommandRequest(BaseModel):
    command: str
    shell: str = "powershell"
    timeout: int = 30

class TaskRequest(BaseModel):
    command: str
    schedule: str  # ISO datetime or cron expression
    name: Optional[str] = None
    type: str = "one_time"  # "one_time" or "recurring"

class RenameRequest(BaseModel):
    new_name: str

class CreateDirRequest(BaseModel):
    path: str


# ── Chat / AI ────────────────────────────────────────────────

@router.post("/chat")
async def chat(body: ChatRequest, _=Depends(require_auth)):
    """Send a message to the AI agent."""
    response = await agent.chat(body.message, body.session_id)
    return {"response": response}

@router.get("/chat/sessions")
async def get_sessions(_=Depends(require_auth)):
    """Get all saved chat sessions."""
    return memory.get_all_sessions()

@router.get("/chat/sessions/{session_id}")
async def get_session_history(session_id: str, _=Depends(require_auth)):
    """Get conversation history for a specific session."""
    return memory.get_history(session_id)

@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, _=Depends(require_auth)):
    """Delete a chat session."""
    memory.clear(session_id)
    return {"success": True}

@router.post("/chat/sessions/{session_id}/rename")
async def rename_session(session_id: str, body: RenameSessionRequest, _=Depends(require_auth)):
    """Rename a chat session."""
    memory.rename_session(session_id, body.new_name)
    return {"success": True}


# ── Commands ─────────────────────────────────────────────────

@router.post("/command")
async def run_command(body: CommandRequest, _=Depends(require_auth)):
    """Execute a shell command."""
    result = command_runner.execute_sync(body.command, body.shell, body.timeout)
    return result

@router.get("/command/history")
async def command_history(limit: int = 20, _=Depends(require_auth)):
    """Get command execution history."""
    return command_runner.get_history(limit)


# ── Files ────────────────────────────────────────────────────

@router.get("/files/drives")
async def get_drives(_=Depends(require_auth)):
    """List available drives."""
    return file_manager.get_drives()

@router.get("/files/list")
async def list_files(path: str = "C:\\Users", _=Depends(require_auth)):
    """List directory contents."""
    return file_manager.list_directory(path)

@router.get("/files/info")
async def file_info(path: str, _=Depends(require_auth)):
    """Get file details."""
    return file_manager.get_file_info(path)

@router.get("/files/download")
async def download_file(path: str, _=Depends(require_auth)):
    """Download a file."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return {"error": "File not found"}
    return FileResponse(str(file_path), filename=file_path.name)

@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    directory: str = Query("C:\\Users"),
    _=Depends(require_auth),
):
    """Upload a file to a directory."""
    try:
        target_dir = Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file.filename

        async with aiofiles.open(target_path, "wb") as f:
            content = await file.read()
            await f.write(content)

        return {"success": True, "path": str(target_path), "size": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/files/delete")
async def delete_file(path: str, _=Depends(require_auth)):
    """Delete a file or directory."""
    return file_manager.delete(path)

@router.post("/files/rename")
async def rename_file(path: str, body: RenameRequest, _=Depends(require_auth)):
    """Rename a file or directory."""
    return file_manager.rename(path, body.new_name)

@router.post("/files/mkdir")
async def create_dir(body: CreateDirRequest, _=Depends(require_auth)):
    """Create a directory."""
    return file_manager.create_directory(body.path)


# ── Screen ───────────────────────────────────────────────────

@router.get("/screen/monitors")
async def list_monitors(_=Depends(require_auth)):
    """List all connected monitors available for streaming."""
    return screen_streamer.list_monitors()


# ── System ───────────────────────────────────────────────────

@router.get("/logs/errors")
async def get_error_logs(_=Depends(require_auth)):
    """Get the persistent error logs."""
    return error_logger.get_error_logs()

@router.get("/system/info")
async def sys_info(_=Depends(require_auth)):
    """Get system information snapshot."""
    return system_monitor.get_snapshot()

@router.get("/settings")
async def get_settings(_=Depends(require_auth)):
    """Get server configuration and settings."""
    from server.config import config
    return {
        "ai_provider": config.AI_PROVIDER,
        "ollama_model": config.OLLAMA_MODEL,
        "ollama_base_url": config.OLLAMA_BASE_URL,
        "has_gemini_key": bool(config.GEMINI_API_KEY),
        "has_openai_key": bool(config.OPENAI_API_KEY),
        "host": config.HOST,
        "port": config.PORT,
        "screen_resolution": f"{config.SCREEN_WIDTH}x{config.SCREEN_HEIGHT}",
        "screen_fps": config.SCREEN_FPS,
        "has_telegram_token": bool(config.TELEGRAM_BOT_TOKEN),
        "telegram_allowed_user": config.ALLOWED_TELEGRAM_USER_ID,
        "tunnel_hostname": config.TUNNEL_HOSTNAME or "Quick Tunnel",
    }


# ── Processes ────────────────────────────────────────────────

@router.get("/processes")
async def get_processes(
    sort_by: str = "memory",
    limit: int = 50,
    search: Optional[str] = None,
    _=Depends(require_auth),
):
    """List running processes."""
    return process_manager.list_processes(sort_by, limit, search)

@router.post("/processes/kill/{pid}")
async def kill_process(pid: int, _=Depends(require_auth)):
    """Kill a process by PID."""
    return process_manager.kill_process(pid)

@router.get("/processes/{pid}")
async def process_details(pid: int, _=Depends(require_auth)):
    """Get process details."""
    return process_manager.get_process_details(pid)


# ── Tasks / Scheduler ───────────────────────────────────────

@router.get("/tasks")
async def list_tasks(_=Depends(require_auth)):
    """List scheduled tasks."""
    return task_scheduler.list_tasks()

@router.post("/tasks")
async def create_task(body: TaskRequest, _=Depends(require_auth)):
    """Create a scheduled task."""
    if body.type == "recurring":
        return task_scheduler.add_recurring_task(body.command, body.schedule, body.name)
    else:
        return task_scheduler.add_one_time_task(body.command, body.schedule, body.name)

@router.delete("/tasks/{task_id}")
async def remove_task(task_id: str, _=Depends(require_auth)):
    """Remove a scheduled task."""
    return task_scheduler.remove_task(task_id)


# ── Skills ───────────────────────────────────────────────────

@router.get("/skills")
async def list_skills_api(_=Depends(require_auth)):
    """List installed skills with their name and description."""
    return get_skills_index()


# ── Notifications ────────────────────────────────────────────

@router.get("/notifications")
async def get_notifications(limit: int = 50, _=Depends(require_auth)):
    """Get notification history."""
    return notifications.get_history(limit)

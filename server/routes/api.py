"""
MIA REST API Routes — Core HTTP endpoints.
"""

import os
import aiofiles
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Query, Request, HTTPException
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
from server.selfmod.approvals import approvals
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

class TaskEnabledRequest(BaseModel):
    enabled: bool

class HeartbeatRequest(BaseModel):
    enabled: Optional[bool] = None
    every_minutes: Optional[int] = None
    active_hours: Optional[str] = None
    deliver_to: Optional[list[str]] = None
    checklist: Optional[str] = None

class TaskRequest(BaseModel):
    command: str
    schedule: str  # ISO datetime or cron expression
    name: Optional[str] = None
    type: str = "one_time"  # "one_time" or "recurring"

class RenameRequest(BaseModel):
    new_name: str

class CreateDirRequest(BaseModel):
    path: str

class ApiKeyRequest(BaseModel):
    api_key: str

class ActiveModelRequest(BaseModel):
    provider: str
    model: Optional[str] = None

class ProviderTestRequest(BaseModel):
    model: Optional[str] = None

class OpenRouterStartRequest(BaseModel):
    callback_url: Optional[str] = None

class OpenRouterFinishRequest(BaseModel):
    code: str

class ClaudeAuthModeRequest(BaseModel):
    mode: str

class ClaudeLoginStartRequest(BaseModel):
    no_browser: bool = False

class ClaudeLoginInputRequest(BaseModel):
    text: str


# ── Chat / AI ────────────────────────────────────────────────

@router.post("/chat")
async def chat(body: ChatRequest, _=Depends(require_auth)):
    """Send a message to the AI agent."""
    response = await agent.chat(body.message, body.session_id)
    return {"response": response}

@router.get("/approvals")
async def get_pending_approvals(_=Depends(require_auth)):
    """Actions waiting for the user's approval (decisions are sent over /ws/chat)."""
    return [approvals.public(r) for r in approvals.pending()]

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

# ── AI Models ────────────────────────────────────────────────

def _provider_call(fn, *args):
    from server.services.ai_providers import ProviderError, provider_status
    try:
        fn(*args)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider_status()

@router.get("/ai/providers")
async def get_ai_providers(_=Depends(require_auth)):
    """Providers, their setup state, and which model MIA is using."""
    from server.services.ai_providers import provider_status
    return provider_status()

@router.post("/ai/providers/{provider_id}/key")
async def save_ai_key(provider_id: str, body: ApiKeyRequest, _=Depends(require_auth)):
    from server.services.ai_providers import save_api_key
    return _provider_call(save_api_key, provider_id, body.api_key)

@router.delete("/ai/providers/{provider_id}/key")
async def delete_ai_key(provider_id: str, _=Depends(require_auth)):
    from server.services.ai_providers import remove_api_key
    return _provider_call(remove_api_key, provider_id)

@router.post("/ai/providers/{provider_id}/test")
async def test_ai_provider(provider_id: str, body: ProviderTestRequest, _=Depends(require_auth)):
    from server.services.ai_providers import ProviderError, test_provider
    try:
        return await test_provider(provider_id, body.model)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/ai/active")
async def set_active_ai(body: ActiveModelRequest, _=Depends(require_auth)):
    from server.services.ai_providers import set_active
    return _provider_call(set_active, body.provider, body.model)

@router.get("/ai/providers/openrouter/models")
async def openrouter_model_list(q: str = "", _=Depends(require_auth)):
    """OpenRouter models that support tools (cached for an hour); `q` filters by name."""
    import asyncio
    from server.services.ai_providers import ProviderError, openrouter_models, search_openrouter_models
    try:
        if q:
            await asyncio.to_thread(openrouter_models)
            return search_openrouter_models(q, limit=50)
        return await asyncio.to_thread(openrouter_models)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))

@router.post("/ai/providers/openrouter/oauth/start")
async def openrouter_oauth_start(body: OpenRouterStartRequest, _=Depends(require_auth)):
    """Start OpenRouter browser sign-in; returns the URL to open."""
    from server.services.ai_providers import openrouter_auth_start
    return {"url": openrouter_auth_start(body.callback_url)}

@router.post("/ai/providers/openrouter/oauth/finish")
async def openrouter_oauth_finish(body: OpenRouterFinishRequest, _=Depends(require_auth)):
    """Exchange the sign-in code for a key and save it."""
    import asyncio
    from server.services.ai_providers import ProviderError, openrouter_auth_finish, provider_status
    try:
        await asyncio.to_thread(openrouter_auth_finish, body.code)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider_status()

@router.post("/ai/providers/anthropic/auth-mode")
async def set_claude_auth(body: ClaudeAuthModeRequest, _=Depends(require_auth)):
    from server.services.ai_providers import set_claude_auth_mode
    return _provider_call(set_claude_auth_mode, body.mode)

@router.post("/ai/providers/anthropic/install-cli")
async def install_claude_cli(_=Depends(require_auth)):
    """Download Anthropic's official `ant` CLI (needed for browser sign-in)."""
    import asyncio
    from server.services.ai_providers import ProviderError, install_ant, provider_status
    try:
        await asyncio.to_thread(install_ant)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider_status()

@router.get("/ai/providers/anthropic/login")
async def claude_login_status(_=Depends(require_auth)):
    from server.services.ai_providers import claude_login
    return claude_login.status()

@router.post("/ai/providers/anthropic/login")
async def claude_login_start(body: ClaudeLoginStartRequest, _=Depends(require_auth)):
    from server.services.ai_providers import ProviderError, claude_login
    try:
        return claude_login.start(body.no_browser)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/ai/providers/anthropic/login/input")
async def claude_login_input(body: ClaudeLoginInputRequest, _=Depends(require_auth)):
    from server.services.ai_providers import ProviderError, claude_login
    try:
        return claude_login.send_input(body.text)
    except ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/ai/providers/anthropic/login")
async def claude_login_cancel(_=Depends(require_auth)):
    from server.services.ai_providers import claude_login
    return claude_login.cancel()

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
    """Remove a scheduled task (the user's own action, so no approval step)."""
    from server.services.scheduler import SchedulerError
    try:
        return task_scheduler.remove_task(task_id)
    except SchedulerError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str, _=Depends(require_auth)):
    """Run a scheduled task immediately (in the background)."""
    from server.services.scheduler import SchedulerError
    try:
        task_scheduler.run_now(task_id)
    except SchedulerError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}

@router.post("/tasks/{task_id}/enabled")
async def set_task_enabled(task_id: str, body: TaskEnabledRequest, _=Depends(require_auth)):
    """Pause or resume a scheduled task."""
    from server.services.scheduler import SchedulerError
    try:
        return task_scheduler.set_enabled(task_id, body.enabled)
    except SchedulerError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/heartbeat")
async def get_heartbeat(_=Depends(require_auth)):
    return task_scheduler.heartbeat_status()

@router.post("/heartbeat")
async def update_heartbeat(body: HeartbeatRequest, _=Depends(require_auth)):
    from server.services.scheduler import SchedulerError
    try:
        return task_scheduler.configure_heartbeat(**body.model_dump())
    except SchedulerError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/heartbeat/run")
async def run_heartbeat_now(_=Depends(require_auth)):
    """Run the heartbeat check once, now (ignores active hours)."""
    return await task_scheduler.run_heartbeat_now()


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

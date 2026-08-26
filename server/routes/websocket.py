"""
MIA WebSocket Routes — Real-time communication endpoints.
"""

import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.auth import require_ws_auth
from server.agent.core import agent
from server.services.screen import screen_streamer
from server.services.input_control import input_controller
from server.services.system_monitor import system_monitor
from server.services.command_runner import command_runner
from server.services.notifications import notifications

router = APIRouter()


# ── Chat WebSocket ───────────────────────────────────────────

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Real-time chat with the AI agent."""
    await websocket.accept()

    if not await require_ws_auth(websocket):
        await websocket.send_json({"error": "Unauthorized"})
        await websocket.close(code=4001)
        return

    # Register for notifications
    notifications.add_client(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id", "default")

            if not message:
                continue

            # Send "thinking" indicator
            await websocket.send_json({
                "type": "status",
                "status": "thinking",
            })

            # Stream the agentic loop back to the client token-by-token
            try:
                async for stream_event in agent.stream_chat(message, session_id):
                    await websocket.send_json(stream_event)
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Agent error: {str(e)}",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  Chat WS error: {e}")
    finally:
        notifications.remove_client(websocket)


# ── Screen Streaming WebSocket ───────────────────────────────

@router.websocket("/ws/screen")
async def ws_screen(websocket: WebSocket):
    """Stream screen frames as binary JPEG data."""
    await websocket.accept()

    if not await require_ws_auth(websocket):
        await websocket.close(code=4001)
        return

    try:
        # Listen for control messages in parallel
        async def listen_controls():
            try:
                while True:
                    data = await websocket.receive_json()
                    action = data.get("action")
                    if action == "set_quality":
                        screen_streamer.set_quality(data.get("quality", 50))
                    elif action == "set_fps":
                        screen_streamer.set_fps(data.get("fps", 30))
                    elif action == "set_scale":
                        screen_streamer.set_scale(data.get("scale", 1.0))
                    elif action == "set_monitor":
                        screen_streamer.set_monitor(data.get("monitor", 1))
                    elif action == "stop":
                        screen_streamer.stop_streaming(websocket)
                        break
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        # Run streaming and control listener concurrently
        await asyncio.gather(
            screen_streamer.start_streaming(websocket),
            listen_controls(),
            return_exceptions=True,
        )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  Screen WS error: {e}")
    finally:
        screen_streamer.stop_streaming(websocket)


# ── Input Control WebSocket ──────────────────────────────────

@router.websocket("/ws/control")
async def ws_control(websocket: WebSocket):
    """Receive mouse/keyboard input events."""
    await websocket.accept()

    if not await require_ws_auth(websocket):
        await websocket.close(code=4001)
        return

    try:
        while True:
            data = await websocket.receive_json()
            input_controller.process_input(data)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  Control WS error: {e}")


# ── System Monitor WebSocket ─────────────────────────────────

@router.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket):
    """Stream real-time system stats."""
    await websocket.accept()

    if not await require_ws_auth(websocket):
        await websocket.close(code=4001)
        return

    try:
        await system_monitor.start_monitoring(websocket, interval=1.0)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  Monitor WS error: {e}")
    finally:
        system_monitor.stop_monitoring(websocket)


# ── Terminal WebSocket ───────────────────────────────────────

@router.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket):
    """Interactive terminal with streaming output."""
    await websocket.accept()

    if not await require_ws_auth(websocket):
        await websocket.close(code=4001)
        return

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command", "")
            shell = data.get("shell", "powershell")

            if command:
                await command_runner.execute_streaming(command, websocket, shell)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  Terminal WS error: {e}")

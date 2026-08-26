"""
MIA Command Runner — Execute shell commands with real-time output.
"""

import asyncio
import subprocess
import time
from typing import Optional
from datetime import datetime


class CommandRunner:
    """Execute and manage shell commands."""

    def __init__(self):
        self.history: list[dict] = []
        self.max_history = 100

    def execute_sync(self, command: str, shell: str = "powershell", timeout: int = 30, cwd: Optional[str] = None) -> dict:
        """Execute a command synchronously."""
        start_time = time.time()
        try:
            if shell == "powershell":
                args = ["powershell", "-NoProfile", "-Command", command]
            else:
                args = command

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=(shell == "cmd"),
                cwd=cwd,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            elapsed = round(time.time() - start_time, 2)
            entry = {
                "command": command,
                "shell": shell,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "duration": elapsed,
                "timestamp": datetime.now().isoformat(),
                "success": result.returncode == 0,
            }
            self._add_history(entry)
            return entry

        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "exit_code": -1,
                "duration": timeout,
                "success": False,
            }
        except Exception as e:
            return {
                "command": command,
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "duration": 0,
                "success": False,
            }

    async def execute_streaming(self, command: str, websocket, shell: str = "powershell"):
        """Execute a command and stream output in real-time via WebSocket."""
        try:
            if shell == "powershell":
                args = ["powershell", "-NoProfile", "-Command", command]
            else:
                args = ["cmd", "/c", command]

            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            async def read_stream(stream, stream_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    try:
                        await websocket.send_json({
                            "type": stream_type,
                            "data": text,
                        })
                    except Exception:
                        break

            await asyncio.gather(
                read_stream(process.stdout, "stdout"),
                read_stream(process.stderr, "stderr"),
            )

            exit_code = await process.wait()
            try:
                await websocket.send_json({
                    "type": "exit",
                    "exit_code": exit_code,
                })
            except Exception:
                pass

        except Exception as e:
            try:
                await websocket.send_json({
                    "type": "error",
                    "data": str(e),
                })
            except Exception:
                pass

    def get_history(self, limit: int = 20) -> list:
        """Get command history."""
        return self.history[-limit:]

    def _add_history(self, entry: dict):
        """Add to history with limit."""
        self.history.append(entry)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]


# Global instance
command_runner = CommandRunner()

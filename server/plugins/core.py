import subprocess
from server.plugins import tool

@tool(
    name="execute_command",
    description="Execute a PowerShell or CMD command on this PC. Use this for any system operations.",
    parameters={
        "command": {"type": "string", "description": "The command to execute"},
        "shell": {"type": "string", "description": "Shell to use: 'powershell' or 'cmd'. Default: powershell", "default": "powershell"},
        "timeout": {"type": "integer", "description": "Max seconds to wait. Default: 30", "default": 30}
    },
    required=["command"]
)
def execute_command(command: str, shell: str = "powershell", timeout: int = 30) -> str:
    """Execute a shell command and return the output."""
    try:
        if shell == "powershell":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            return output if output else "✅ Command executed successfully (no output)."
        else:
            return f"❌ Exit code {result.returncode}\nOutput: {output}\nError: {error}"

    except subprocess.TimeoutExpired:
        return f"⚠️ Command timed out after {timeout} seconds."
    except Exception as e:
        return f"❌ Error: {str(e)}"

@tool(
    name="start_application",
    description="Start an application by name or path (e.g., 'chrome', 'notepad', 'C:/path/to/app.exe').",
    parameters={
        "path_or_name": {"type": "string", "description": "App name or path"}
    },
    required=["path_or_name"]
)
def start_application(path_or_name: str) -> str:
    """Start an application."""
    try:
        # Common app aliases
        aliases = {
            "chrome": "start chrome",
            "firefox": "start firefox",
            "notepad": "notepad",
            "explorer": "explorer",
            "cmd": "start cmd",
            "powershell": "start powershell",
            "calculator": "calc",
            "paint": "mspaint",
            "task manager": "taskmgr",
            "settings": "start ms-settings:",
            "vscode": "code",
            "code": "code",
        }

        cmd = aliases.get(path_or_name.lower(), f'start "" "{path_or_name}"')
        subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return f"✅ Launched: {path_or_name}"

    except Exception as e:
        return f"❌ Error starting application: {str(e)}"

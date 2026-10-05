"""
Helpers dynamic tools are allowed to import.

Everything here goes through MIA's safety guard, so a dynamic tool that deletes a file or
runs a destructive command still triggers the same approval as MIA doing it directly.
"""


def call_tool(tool_name: str, **args) -> str:
    """Call another MIA tool by name, e.g. call_tool("read_file", file_path="notes.txt")."""
    from server.agent.tools import execute_tool
    from server.selfmod.guard import current_session
    return execute_tool(tool_name, args, current_session())

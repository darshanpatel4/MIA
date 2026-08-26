"""
MIA Tools — Plugin loader and tool registry exposing.
"""
from server.plugins import TOOL_REGISTRY, load_plugins

# Load all plugins
load_plugins()

def get_tools_for_gemini() -> list:
    """Convert tool registry to Gemini function declarations."""
    declarations = []
    for name, tool in TOOL_REGISTRY.items():
        params = {}
        required = tool.get("required", [])
        for param_name, param_info in tool.get("parameters", {}).items():
            param_schema = {"type": param_info["type"].upper(), "description": param_info["description"]}
            params[param_name] = param_schema

        declaration = {
            "name": name,
            "description": tool["description"],
            "parameters": {
                "type": "OBJECT",
                "properties": params,
                "required": required,
            } if params else None
        }
        declarations.append(declaration)
    return declarations

def get_tools_for_openai() -> list:
    """Convert tool registry to OpenAI function format."""
    tools = []
    for name, tool in TOOL_REGISTRY.items():
        params = {}
        for param_name, param_info in tool.get("parameters", {}).items():
            params[param_name] = {
                "type": param_info["type"],
                "description": param_info["description"],
            }

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": tool.get("required", []),
                },
            },
        })
    return tools

def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool by name with given arguments."""
    if tool_name not in TOOL_REGISTRY:
        return f"❌ Unknown tool: {tool_name}"

    tool = TOOL_REGISTRY[tool_name]
    func = tool["function"]

    # Apply defaults for missing optional params
    for param_name, param_info in tool.get("parameters", {}).items():
        if param_name not in arguments and "default" in param_info:
            arguments[param_name] = param_info["default"]

    try:
        result = func(**arguments)
        return result
    except Exception as e:
        return f"❌ Tool error ({tool_name}): {str(e)}"

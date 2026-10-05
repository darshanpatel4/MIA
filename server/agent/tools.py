"""
MIA Tools — Plugin loader and tool registry exposing.
"""
from server.plugins import TOOL_REGISTRY, load_plugins
from server.selfmod import paths as selfmod_paths
from server.selfmod.dynamic_tools import load_all as load_dynamic_tools
from server.selfmod.guard import run_tool

# Core write-protection first, then built-in plugins, then the tools MIA wrote for itself
selfmod_paths.install_audit_hook()
load_plugins()
load_dynamic_tools()

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

def get_tools_for_anthropic() -> list:
    """Convert tool registry to Claude tool definitions.

    Inputs stream as they are generated (eager_input_streaming), so the API no longer
    validates them — run check_tool_args() on every call before executing it.
    """
    tools = []
    for name, tool in TOOL_REGISTRY.items():
        properties = {
            param_name: {"type": param_info["type"], "description": param_info["description"]}
            for param_name, param_info in tool.get("parameters", {}).items()
        }
        tools.append({
            "name": name,
            "description": tool["description"],
            "eager_input_streaming": True,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": tool.get("required", []),
            },
        })
    return tools

_JSON_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}

def check_tool_args(tool_name: str, arguments) -> str | None:
    """Validate model-supplied arguments against the tool's schema. Returns a problem, or None if valid."""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return f"unknown tool {tool_name}"
    if not isinstance(arguments, dict):
        return "arguments must be a JSON object"
    params = tool.get("parameters", {})
    missing = [p for p in tool.get("required", []) if p not in arguments]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    for key, value in arguments.items():
        if key not in params:
            return f"unknown argument: {key}"
        is_valid = _JSON_TYPES.get(params[key]["type"])
        if is_valid and not is_valid(value):
            return f"argument {key} must be of type {params[key]['type']}"
    return None

def execute_tool(tool_name: str, arguments: dict, session_id: str = "default") -> str:
    """Execute a tool by name with given arguments, through the self-modification safety guard."""
    if tool_name not in TOOL_REGISTRY:
        return f"❌ Unknown tool: {tool_name}"

    tool = TOOL_REGISTRY[tool_name]
    func = tool["function"]

    # Apply defaults for missing optional params
    for param_name, param_info in tool.get("parameters", {}).items():
        if param_name not in arguments and "default" in param_info:
            arguments[param_name] = param_info["default"]

    try:
        return run_tool(tool_name, func, arguments, session_id)
    except Exception as e:
        return f"❌ Tool error ({tool_name}): {str(e)}"

import importlib
import pkgutil
from typing import Callable, Dict, Any, List

# Central registry for all AI tools
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}

def tool(name: str, description: str, parameters: Dict[str, Any] = None, required: List[str] = None):
    """
    Decorator to register a function as an AI tool.
    
    Args:
        name: The name of the tool (must match function name ideally)
        description: A clear description for the LLM
        parameters: A dictionary of parameter schemas
        required: A list of required parameter names
    """
    if parameters is None:
        parameters = {}
    if required is None:
        required = []
        
    def decorator(func: Callable):
        TOOL_REGISTRY[name] = {
            "function": func,
            "description": description,
            "parameters": parameters,
            "required": required
        }
        return func
    return decorator

def load_plugins():
    """Dynamically load all modules in the plugins package so they register their tools."""
    import server.plugins
    for _, module_name, _ in pkgutil.iter_modules(server.plugins.__path__):
        importlib.import_module(f"server.plugins.{module_name}")

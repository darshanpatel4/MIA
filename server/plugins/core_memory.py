from server.plugins import tool
from server.agent.memory import memory

@tool(
    name="save_core_memory",
    description="Save a long-term fact or preference about the user to Core Memory (e.g., their name, OS, coding style). This will be remembered permanently.",
    parameters={
        "fact_key": {"type": "string", "description": "A short, unique identifier for the fact (e.g., 'user_name', 'preferred_os', 'project_path')."},
        "fact_value": {"type": "string", "description": "The actual value or detail to remember (e.g., 'Alex', 'Windows 11', 'Use functional programming')."}
    },
    required=["fact_key", "fact_value"]
)
def save_core_memory(fact_key: str, fact_value: str) -> str:
    """Save a fact to the persistent core memory."""
    try:
        memory.set_persistent(fact_key, fact_value)
        return f"✅ Core memory updated successfully: {fact_key} = {fact_value}"
    except Exception as e:
        return f"❌ Failed to save to core memory: {str(e)}"

@tool(
    name="read_core_memory",
    description="Read all currently saved long-term facts about the user from Core Memory.",
    parameters={}
)
def read_core_memory() -> str:
    """Read all persistent core memory facts."""
    try:
        data = memory.persistent
        if not data:
            return "Core memory is currently empty."
        
        result = "Current Core Memory:\n"
        for k, v in data.items():
            result += f"- {k}: {v}\n"
        return result
    except Exception as e:
        return f"❌ Failed to read core memory: {str(e)}"

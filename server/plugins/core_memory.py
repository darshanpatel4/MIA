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

@tool(
    name="recall_memory",
    description=(
        "Search long-term Core Memory by meaning, not just exact wording — use this when the current "
        "system prompt didn't already include a saved fact you suspect exists (e.g. the user references "
        "something from a past conversation, or memory has grown large enough that older facts may have "
        "been left out of context)."
    ),
    parameters={
        "query": {"type": "string", "description": "What to search for, in natural language (e.g. 'preferred code editor')."}
    },
    required=["query"]
)
def recall_memory(query: str) -> str:
    """Semantically search persistent core memory."""
    try:
        results = memory.search_persistent(query)
        if not results:
            return f"No relevant memories found for: {query}"

        lines = [f"Memories relevant to '{query}':"]
        for key, value, score in results:
            lines.append(f"- {key}: {value} (relevance: {score:.2f})")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to search core memory: {str(e)}"

@tool(
    name="search_past_conversations",
    description=(
        "Search across ALL past chat sessions (not just the current one) by meaning, for when the user "
        "references something discussed before — 'like I mentioned before', 'what did we talk about "
        "regarding X', 'last time we...'. Returns matching past exchanges with which session they're from."
    ),
    parameters={
        "query": {"type": "string", "description": "What to search for, in natural language."}
    },
    required=["query"]
)
def search_past_conversations(query: str) -> str:
    """Semantically search the cross-session conversation index."""
    try:
        results = memory.search_conversations(query)
        if not results:
            return f"No past conversations found relevant to: {query}"

        import datetime
        lines = [f"Past exchanges relevant to '{query}':"]
        for entry in results:
            when = datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"\n[session {entry['session_id']}, {when}, relevance {entry['score']:.2f}]\n"
                f"User: {entry['user_message']}\n"
                f"Assistant: {entry['assistant_response']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to search past conversations: {str(e)}"

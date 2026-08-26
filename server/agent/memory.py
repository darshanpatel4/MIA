"""
MIA Memory — Conversation history and persistent memory.
"""

import json
from pathlib import Path
from typing import Any
from server.config import config


class ConversationMemory:
    """Sliding window conversation history per session + global persistent core memory."""

    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self.persistent: dict[str, Any] = {}
        self._load_persistent()
        
        self.sessions_dir = config.MEMORY_FILE.parent / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}  # session_id -> list of messages

    # ── Session Management (Chat History) ────────────────────────

    def _get_session_file(self, session_id: str) -> Path:
        """Get the file path for a specific session."""
        return self.sessions_dir / f"{session_id}.json"

    def _load_session(self, session_id: str) -> list[dict[str, Any]]:
        """Load session messages into cache from disk."""
        if session_id in self._cache:
            return self._cache[session_id]
            
        file_path = self._get_session_file(session_id)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cache[session_id] = data.get("messages", [])
                    return self._cache[session_id]
            except Exception:
                pass
        
        self._cache[session_id] = []
        return self._cache[session_id]

    def _save_session(self, session_id: str):
        """Save session messages and auto-generate name to disk."""
        messages = self._cache.get(session_id, [])
        file_path = self._get_session_file(session_id)
        
        name = "New Chat"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    name = old_data.get("name", "New Chat")
            except Exception:
                pass
                
        # If it's a new chat, generate name from the first user message
        if name == "New Chat" and messages:
            first_msg = messages[0]["content"]
            words = first_msg.split()[:5]
            name = " ".join(words).title() + ("..." if len(words) == 5 else "")

        data = {
            "id": session_id,
            "name": name,
            "messages": messages
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_user_message(self, content: str, session_id: str = "default"):
        """Add a user message to history."""
        msgs = self._load_session(session_id)
        msgs.append({"role": "user", "content": content})
        self._trim(session_id)
        self._save_session(session_id)

    def add_assistant_message(self, content: str, session_id: str = "default"):
        """Add an assistant message to history."""
        msgs = self._load_session(session_id)
        msgs.append({"role": "assistant", "content": content})
        self._trim(session_id)
        self._save_session(session_id)

    def add_tool_call(self, tool_name: str, args: dict, result: str, session_id: str = "default"):
        """Add a tool call and its result to history."""
        msgs = self._load_session(session_id)
        msgs.append({
            "role": "tool",
            "tool_name": tool_name,
            "args": args,
            "result": result,
        })
        self._trim(session_id)
        self._save_session(session_id)

    def get_history(self, session_id: str = "default") -> list[dict[str, Any]]:
        """Get conversation history for context."""
        return self._load_session(session_id).copy()

    def get_history_for_model(self, session_id: str = "default") -> list[dict[str, str]]:
        """Get history formatted for the AI model."""
        msgs = self._load_session(session_id)
        formatted = []
        for msg in msgs:
            if msg["role"] in ("user", "assistant"):
                formatted.append({"role": msg["role"], "content": msg["content"]})
            elif msg["role"] == "tool":
                formatted.append({
                    "role": "user",
                    "content": f"[Tool Result: {msg['tool_name']}]\n{msg['result']}"
                })
        return formatted

    def clear(self, session_id: str = "default"):
        """Clear conversation history for a session."""
        self._cache[session_id] = []
        file_path = self._get_session_file(session_id)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
                
    def rename_session(self, session_id: str, new_name: str):
        """Rename a chat session."""
        file_path = self._get_session_file(session_id)
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["name"] = new_name
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
                
    def get_all_sessions(self) -> list[dict]:
        """List all saved sessions."""
        sessions = []
        if self.sessions_dir.exists():
            for f in self.sessions_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        data = json.load(file)
                        
                        # Use file modification time as updated_at
                        updated_at = f.stat().st_mtime
                        
                        sessions.append({
                            "id": data.get("id", f.stem),
                            "name": data.get("name", "New Chat"),
                            "updated_at": updated_at
                        })
                except Exception:
                    pass
        # Sort by updated_at descending
        sessions.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return sessions

    def _trim(self, session_id: str):
        """Trim history to max_messages."""
        msgs = self._cache.get(session_id, [])
        if len(msgs) > self.max_messages:
            self._cache[session_id] = msgs[-self.max_messages:]

    # ── Core Memory (Persistent Facts) ───────────────────────────

    def set_persistent(self, key: str, value: Any):
        """Store persistent data (survives restarts)."""
        self.persistent[key] = value
        self._save_persistent()

    def get_persistent(self, key: str, default: Any = None) -> Any:
        """Retrieve persistent data."""
        return self.persistent.get(key, default)

    def _load_persistent(self):
        """Load persistent core memory from disk."""
        try:
            if config.MEMORY_FILE.exists():
                with open(config.MEMORY_FILE, "r", encoding="utf-8") as f:
                    self.persistent = json.load(f)
        except Exception:
            self.persistent = {}

    def _save_persistent(self):
        """Save persistent core memory to disk."""
        try:
            config.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(config.MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.persistent, f, indent=2)
        except Exception:
            pass


# Global memory instance
memory = ConversationMemory()

"""
MIA Memory — Conversation history and persistent memory.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any
from server.config import config
from server.agent.embeddings import embed_text, cosine_similarity

# How many facts before semantic search kicks in instead of dumping everything.
# Below this, all facts fit comfortably in the prompt with no retrieval needed.
SEMANTIC_SEARCH_THRESHOLD = 8
TOP_K_MEMORIES = 5
MIN_RELEVANCE_SCORE = 0.4

# Cross-session conversation index — how much to keep and how much to embed per turn.
MAX_INDEXED_EXCHANGES = 2000
MAX_INDEXED_RESPONSE_CHARS = 800
TOP_K_CONVERSATIONS = 5
MIN_CONVERSATION_SCORE = 0.45


class ConversationMemory:
    """Sliding window conversation history per session + global persistent core memory."""

    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self.persistent: dict[str, Any] = {}
        self._embeddings: dict[str, list[float]] = {}
        self.conversation_index: list[dict[str, Any]] = []
        self._load_persistent()
        self._load_embeddings()
        self._load_conversation_index()

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

    def add_assistant_message(self, content: str, session_id: str = "default", reasoning: str | None = None):
        """Add an assistant message to history.

        `reasoning` is the model's hidden reasoning (DeepSeek thinking mode), which that API
        requires to be sent back on later requests; other providers never see it.
        """
        msgs = self._load_session(session_id)
        msg = {"role": "assistant", "content": content}
        if reasoning:
            msg["reasoning"] = reasoning
        msgs.append(msg)
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

    def get_history_for_model(self, session_id: str = "default", include_reasoning: bool = False) -> list[dict[str, str]]:
        """Get history formatted for the AI model.

        include_reasoning: add `reasoning_content` to every assistant message (empty when none
        was stored) — required by DeepSeek's thinking mode when tools are used.
        """
        msgs = self._load_session(session_id)
        formatted = []
        for msg in msgs:
            if msg["role"] in ("user", "assistant"):
                entry = {"role": msg["role"], "content": msg["content"]}
                if include_reasoning and msg["role"] == "assistant":
                    entry["reasoning_content"] = msg.get("reasoning", "")
                formatted.append(entry)
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
        """Store persistent data (survives restarts) and embed it for semantic recall."""
        self.persistent[key] = value
        self._save_persistent()

        # Embed "key: value" so search matches on meaning, not just exact key lookups.
        vector = embed_text(f"{key}: {value}")
        if vector is not None:
            self._embeddings[key] = vector
            self._save_embeddings()

    def get_persistent(self, key: str, default: Any = None) -> Any:
        """Retrieve persistent data."""
        return self.persistent.get(key, default)

    def search_persistent(self, query: str, top_k: int = TOP_K_MEMORIES) -> list[tuple[str, Any, float]]:
        """Semantic search over persistent facts. Returns [(key, value, score), ...] sorted by relevance.

        Facts saved before embeddings existed (or if embedding failed) are skipped here —
        they're still readable via get_persistent/read_core_memory, just not searchable.
        """
        query_vector = embed_text(query)
        if query_vector is None or not self._embeddings:
            return []

        scored = []
        for key, vector in self._embeddings.items():
            if key not in self.persistent:
                continue  # stale embedding for a deleted fact
            score = cosine_similarity(query_vector, vector)
            if score >= MIN_RELEVANCE_SCORE:
                scored.append((key, self.persistent[key], score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:top_k]

    def relevant_memories_for_prompt(self, query: str) -> dict[str, Any]:
        """What should actually go into the system prompt for this turn.

        Small memory sets are shown in full (no retrieval overhead needed); once it
        grows past the threshold, only the top-K semantically relevant facts are used.
        """
        if len(self.persistent) <= SEMANTIC_SEARCH_THRESHOLD:
            return dict(self.persistent)

        results = self.search_persistent(query)
        if not results:
            # Embedding unavailable/failed — fall back to showing everything
            # rather than silently hiding all long-term memory.
            return dict(self.persistent)
        return {key: value for key, value, _score in results}

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

    @property
    def _embeddings_file(self) -> Path:
        return config.MEMORY_FILE.parent / "memory_embeddings.json"

    def _load_embeddings(self):
        """Load fact embeddings from disk."""
        try:
            if self._embeddings_file.exists():
                with open(self._embeddings_file, "r", encoding="utf-8") as f:
                    self._embeddings = json.load(f)
        except Exception:
            self._embeddings = {}

    def _save_embeddings(self):
        """Save fact embeddings to disk."""
        try:
            self._embeddings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._embeddings_file, "w", encoding="utf-8") as f:
                json.dump(self._embeddings, f)
        except Exception:
            pass

    # ── Cross-Session Conversation Search ─────────────────────────

    def index_exchange(self, session_id: str, user_message: str, assistant_response: str):
        """Embed and index one user/assistant exchange so it's semantically searchable later,
        across sessions. Called after each successful turn; failures here are non-fatal —
        indexing is a bonus, not required for the chat itself to work.
        """
        response = (assistant_response or "")[:MAX_INDEXED_RESPONSE_CHARS]
        text = f"User: {user_message}\nAssistant: {response}"

        vector = embed_text(text)
        if vector is None:
            return

        self.conversation_index.append({
            "id": uuid.uuid4().hex[:12],
            "session_id": session_id,
            "timestamp": time.time(),
            "user_message": user_message,
            "assistant_response": response,
            "embedding": vector,
        })

        # Cap growth — drop the oldest entries once past the limit.
        if len(self.conversation_index) > MAX_INDEXED_EXCHANGES:
            self.conversation_index = self.conversation_index[-MAX_INDEXED_EXCHANGES:]

        self._save_conversation_index()

    def search_conversations(self, query: str, top_k: int = TOP_K_CONVERSATIONS) -> list[dict[str, Any]]:
        """Semantic search across all past indexed exchanges (every session). Returns entries
        sorted by relevance, each with session_id/timestamp/user_message/assistant_response/score.
        """
        query_vector = embed_text(query)
        if query_vector is None or not self.conversation_index:
            return []

        scored = []
        for entry in self.conversation_index:
            score = cosine_similarity(query_vector, entry["embedding"])
            if score >= MIN_CONVERSATION_SCORE:
                scored.append({**{k: v for k, v in entry.items() if k != "embedding"}, "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @property
    def _conversation_index_file(self) -> Path:
        return config.MEMORY_FILE.parent / "conversation_index.json"

    def _load_conversation_index(self):
        """Load the conversation search index from disk."""
        try:
            if self._conversation_index_file.exists():
                with open(self._conversation_index_file, "r", encoding="utf-8") as f:
                    self.conversation_index = json.load(f)
        except Exception:
            self.conversation_index = []

    def _save_conversation_index(self):
        """Save the conversation search index to disk."""
        try:
            self._conversation_index_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._conversation_index_file, "w", encoding="utf-8") as f:
                json.dump(self.conversation_index, f)
        except Exception:
            pass


# Global memory instance
memory = ConversationMemory()

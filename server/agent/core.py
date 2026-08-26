"""
MIA Agent Core — Multi-model agentic loop with function calling.
Supports Gemini, OpenAI, and Ollama.
"""

import json
import asyncio
import threading
from typing import AsyncGenerator, Iterator

from server.config import config
from server.agent.prompts import get_system_prompt
from server.agent.memory import memory
from server.agent.tools import TOOL_REGISTRY, execute_tool, get_tools_for_gemini, get_tools_for_openai
from server.services.error_logger import error_logger

MAX_ITERATIONS = 10


async def _stream_sync_iter(sync_iter: Iterator) -> AsyncGenerator:
    """Bridge a blocking/synchronous iterator (SDK stream) onto the asyncio event loop.

    Runs the blocking iteration in a background thread and forwards each item
    through an asyncio.Queue so callers can `async for` over it without blocking.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def worker():
        try:
            for item in sync_iter:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is _SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        yield item


class MIAAgent:
    """The AI brain — processes natural language and executes tools."""

    def __init__(self):
        self.provider = config.AI_PROVIDER
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the AI model client."""
        try:
            if self.provider == "gemini":
                from google import genai
                self._client = genai.Client(api_key=config.GEMINI_API_KEY)
                self._model = "gemini-2.5-flash"
            elif self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=config.OPENAI_API_KEY)
                self._model = "gpt-4o"
            elif self.provider == "ollama":
                from openai import OpenAI
                self._client = OpenAI(
                    base_url=f"{config.OLLAMA_BASE_URL}/v1",
                    api_key="ollama"
                )
                self._model = config.OLLAMA_MODEL
            print(f"  ✅ AI Agent initialized: {self.provider} ({self._model})")
        except Exception as e:
            print(f"  ❌ AI Agent init failed: {e}")
            self._client = None

    async def chat(self, user_message: str, session_id: str = "default") -> str:
        """Process a user message and return the final text (non-streaming callers, e.g. REST API)."""
        final_message = "Done."
        async for event in self.stream_chat(user_message, session_id):
            if event["type"] == "done":
                final_message = event["message"]
            elif event["type"] == "error":
                final_message = f"❌ {event['message']}"
        return final_message

    async def stream_chat(self, user_message: str, session_id: str = "default") -> AsyncGenerator[dict, None]:
        """Stream the agentic loop as a sequence of events:
        {"type": "chunk", "content": str}          — a piece of assistant text
        {"type": "tool_call", "tool_name", "tool_args"} — a tool is about to run
        {"type": "tool_result", "tool_name", "result"}  — a tool finished
        {"type": "done", "message": str}            — final full assistant text
        {"type": "error", "message": str}            — something went wrong
        """
        if not self._client:
            yield {"type": "error", "message": "AI Agent is not initialized. Check your API key in .env"}
            return

        memory.add_user_message(user_message, session_id)

        full_text = ""
        try:
            if self.provider == "gemini":
                stream = self._stream_chat_gemini(user_message, session_id)
            elif self.provider in ("openai", "ollama"):
                stream = self._stream_chat_openai(user_message, session_id)
            else:
                yield {"type": "error", "message": "Unknown AI provider"}
                return

            async for event in stream:
                if event["type"] == "done":
                    full_text = event["message"]
                yield event

            memory.add_assistant_message(full_text, session_id)

        except Exception as e:
            friendly_error = error_logger.log_error(e, context="Agent Core")
            yield {"type": "error", "message": friendly_error}

    async def _stream_chat_gemini(self, user_message: str, session_id: str) -> AsyncGenerator[dict, None]:
        """Gemini streaming agentic loop with function calling."""
        from google.genai import types

        tool_functions = [tool_info["function"] for tool_info in TOOL_REGISTRY.values()]

        contents = []
        for msg in memory.get_history_for_model(session_id)[:-1]:  # Exclude the latest (added separately)
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])]
            ))
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)]
        ))

        config_obj = types.GenerateContentConfig(
            system_instruction=get_system_prompt(),
            tools=tool_functions,
            temperature=0.7,
            # We execute tool calls ourselves (to stream tool_call/tool_result
            # events); without this, the SDK's Automatic Function Calling runs
            # the same tool internally too, and both results get merged into
            # one response — duplicating output whenever a tool is used.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        full_text = ""
        iteration = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1

            turn_text = ""
            function_calls = []

            sync_stream = self._client.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config_obj,
            )
            async for chunk in _stream_sync_iter(sync_stream):
                if chunk.function_calls:
                    function_calls.extend(chunk.function_calls)
                if chunk.text:
                    turn_text += chunk.text
                    full_text += chunk.text
                    yield {"type": "chunk", "content": chunk.text}

            if function_calls:
                model_parts = []
                if turn_text:
                    model_parts.append(types.Part.from_text(text=turn_text))
                for fc in function_calls:
                    model_parts.append(types.Part.from_function_call(name=fc.name, args=dict(fc.args) if fc.args else {}))
                contents.append(types.Content(role="model", parts=model_parts))

                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    yield {"type": "tool_call", "tool_name": tool_name, "tool_args": tool_args}
                    print(f"  🔧 Tool call: {tool_name}({tool_args})")
                    result = execute_tool(tool_name, tool_args)
                    print(f"  📤 Result: {result[:200]}")
                    yield {"type": "tool_result", "tool_name": tool_name, "result": result}

                    memory.add_tool_call(tool_name, tool_args, result, session_id)

                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(
                            name=tool_name,
                            response={"result": result}
                        )]
                    ))
                # Loop again so the model can respond to the tool results
            else:
                yield {"type": "done", "message": full_text or "Done."}
                return

        yield {"type": "done", "message": full_text or "⚠️ Reached max tool iterations. Here's what I've done so far."}

    async def _stream_chat_openai(self, user_message: str, session_id: str) -> AsyncGenerator[dict, None]:
        """OpenAI/Ollama streaming agentic loop with function calling."""
        messages = [{"role": "system", "content": get_system_prompt()}]
        messages.extend(memory.get_history_for_model(session_id))

        tools = get_tools_for_openai()
        full_text = ""
        iteration = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1

            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": 0.7,
                "stream": True,
            }

            # Only add tools for models that support them
            if self.provider == "openai" or (self.provider == "ollama" and tools):
                kwargs["tools"] = tools

            turn_text = ""
            tool_calls_acc: dict[int, dict] = {}
            finish_reason = None

            sync_stream = self._client.chat.completions.create(**kwargs)
            async for chunk in _stream_sync_iter(sync_stream):
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta

                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                if delta and delta.content:
                    turn_text += delta.content
                    full_text += delta.content
                    yield {"type": "chunk", "content": delta.content}

                if delta and delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_calls_acc[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls_acc[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls_acc[idx]["arguments"] += tc_delta.function.arguments

            if finish_reason == "tool_calls" and tool_calls_acc:
                tool_calls_list = [
                    {
                        "id": tool_calls_acc[idx]["id"],
                        "type": "function",
                        "function": {
                            "name": tool_calls_acc[idx]["name"],
                            "arguments": tool_calls_acc[idx]["arguments"],
                        },
                    }
                    for idx in sorted(tool_calls_acc)
                ]

                messages.append({
                    "role": "assistant",
                    "content": turn_text or None,
                    "tool_calls": tool_calls_list,
                })

                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    except json.JSONDecodeError:
                        tool_args = {}

                    yield {"type": "tool_call", "tool_name": tool_name, "tool_args": tool_args}
                    print(f"  🔧 Tool call: {tool_name}({tool_args})")
                    result = execute_tool(tool_name, tool_args)
                    print(f"  📤 Result: {result[:200]}")
                    yield {"type": "tool_result", "tool_name": tool_name, "result": result}

                    memory.add_tool_call(tool_name, tool_args, result, session_id)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                # Loop again so the model can respond to the tool results
            else:
                yield {"type": "done", "message": full_text or "Done."}
                return

        yield {"type": "done", "message": full_text or "⚠️ Reached max tool iterations."}


# Global agent instance
agent = MIAAgent()

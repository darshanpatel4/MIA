"""
MIA Agent Core — Multi-model agentic loop with function calling.
Supports Gemini, OpenAI, and Ollama.
"""

import os
import json
import asyncio
import threading
from typing import AsyncGenerator, Iterator

from server.config import config
from server.agent.prompts import get_system_prompt
from server.agent.memory import memory
from server.agent.tools import (
    TOOL_REGISTRY, check_tool_args, execute_tool,
    get_tools_for_anthropic, get_tools_for_gemini, get_tools_for_openai,
)
from server.services.error_logger import error_logger
from server.selfmod.approvals import approvals
from server.services.ai_providers import make_anthropic_client, make_deepseek_client, make_openrouter_client

MAX_ITERATIONS = 10

# Claude models that support server-side refusal fallbacks (`fallbacks: "default"`).
CLAUDE_FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1", "claude-fable-5"}
CLAUDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"


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
        self._init_client()

    def reload(self):
        """Re-read the provider/model/credentials from config (after a change in Settings)."""
        self._init_client()

    @property
    def model(self) -> str:
        return getattr(self, "_model", "")

    @property
    def init_error(self) -> str | None:
        return self._init_error

    def _init_client(self):
        """Initialize the AI model client."""
        self.provider = config.AI_PROVIDER
        self._client = None
        self._init_error = None
        try:
            if self.provider == "gemini":
                from google import genai
                self._client = genai.Client(api_key=config.GEMINI_API_KEY)
                self._model = config.GEMINI_MODEL
            elif self.provider == "openai":
                from openai import OpenAI
                self._client = OpenAI(api_key=config.OPENAI_API_KEY)
                self._model = config.OPENAI_MODEL
            elif self.provider == "anthropic":
                self._model = config.ANTHROPIC_MODEL
                self._client = make_anthropic_client()
            elif self.provider == "openrouter":
                self._model = config.OPENROUTER_MODEL
                self._client = make_openrouter_client()
            elif self.provider == "deepseek":
                self._model = config.DEEPSEEK_MODEL
                self._client = make_deepseek_client()
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
            self._init_error = str(e)

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
        {"type": "approval_request", "request": dict}   — a tool call is waiting for the user's approval
        {"type": "done", "message": str}            — final full assistant text
        {"type": "error", "message": str}            — something went wrong
        """
        if not self._client:
            detail = f" ({self._init_error})" if self._init_error else ""
            yield {"type": "error", "message": f"AI Agent is not initialized{detail}. Set up a model in Settings → AI Models."}
            return

        memory.add_user_message(user_message, session_id)

        full_text = ""
        try:
            if self.provider == "gemini":
                stream = self._stream_chat_gemini(user_message, session_id)
            elif self.provider in ("openai", "ollama", "openrouter", "deepseek"):
                stream = self._stream_chat_openai(user_message, session_id)
            elif self.provider == "anthropic":
                stream = self._stream_chat_anthropic(user_message, session_id)
            else:
                yield {"type": "error", "message": "Unknown AI provider"}
                return

            reasoning = None
            async for event in stream:
                if event["type"] == "done":
                    full_text = event["message"]
                    reasoning = event.pop("reasoning", None)  # kept for memory, not sent to the UI
                yield event

            memory.add_assistant_message(full_text, session_id, reasoning=reasoning)
            memory.index_exchange(session_id, user_message, full_text)

        except Exception as e:
            friendly_error = error_logger.log_error(e, context="Agent Core")
            yield {"type": "error", "message": friendly_error}

    async def _stream_chat_gemini(self, user_message: str, session_id: str) -> AsyncGenerator[dict, None]:
        """Gemini streaming agentic loop with function calling."""
        from google.genai import types

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
            system_instruction=get_system_prompt(user_message),
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
            # Rebuilt every turn so a dynamic tool MIA just created can be used right away.
            config_obj.tools = [tool_info["function"] for tool_info in TOOL_REGISTRY.values()]

            # Keep the *original* Part objects (not rebuilt copies) — newer "thinking"
            # models attach a thought_signature to parts that must be replayed back
            # unchanged on the next turn, or the API rejects the request with a 400.
            turn_parts = []
            function_call_parts = []

            sync_stream = self._client.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config_obj,
            )
            async for chunk in _stream_sync_iter(sync_stream):
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                for part in chunk.candidates[0].content.parts:
                    turn_parts.append(part)
                    if part.function_call:
                        function_call_parts.append(part)
                    elif part.text:
                        full_text += part.text
                        yield {"type": "chunk", "content": part.text}

            if function_call_parts:
                contents.append(types.Content(role="model", parts=turn_parts))

                for part in function_call_parts:
                    fc = part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    yield {"type": "tool_call", "tool_name": tool_name, "tool_args": tool_args}
                    print(f"  🔧 Tool call: {tool_name}({tool_args})")
                    result = execute_tool(tool_name, tool_args, session_id)
                    print(f"  📤 Result: {result[:200]}")
                    yield {"type": "tool_result", "tool_name": tool_name, "result": result}
                    for request in approvals.drain_new():
                        yield {"type": "approval_request", "request": approvals.public(request)}

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
        # DeepSeek thinking mode: with tools, every earlier assistant turn must carry its reasoning_content.
        deepseek = self.provider == "deepseek"
        messages = [{"role": "system", "content": get_system_prompt(user_message)}]
        messages.extend(memory.get_history_for_model(session_id, include_reasoning=deepseek))

        full_text = ""
        iteration = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1
            tools = get_tools_for_openai()  # rebuilt every turn so newly created dynamic tools show up

            kwargs = {
                "model": self._model,
                "messages": messages,
                "stream": True,
            }
            if deepseek:
                kwargs["reasoning_effort"] = "high"
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            elif self.provider != "openrouter":
                # OpenRouter routes to models (e.g. Claude Opus 5) that reject sampling parameters;
                # DeepSeek's thinking mode ignores them
                kwargs["temperature"] = 0.7

            # Only add tools for models that support them
            if self.provider in ("openai", "openrouter", "deepseek") or (self.provider == "ollama" and tools):
                kwargs["tools"] = tools

            turn_text = ""
            turn_reasoning = ""
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

                if delta and getattr(delta, "reasoning_content", None):
                    turn_reasoning += delta.reasoning_content  # DeepSeek's hidden thinking — not shown, but replayed

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

                assistant_turn = {
                    "role": "assistant",
                    "content": turn_text or None,
                    "tool_calls": tool_calls_list,
                }
                if deepseek:
                    assistant_turn["reasoning_content"] = turn_reasoning
                messages.append(assistant_turn)

                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    except json.JSONDecodeError:
                        tool_args = {}

                    yield {"type": "tool_call", "tool_name": tool_name, "tool_args": tool_args}
                    print(f"  🔧 Tool call: {tool_name}({tool_args})")
                    result = execute_tool(tool_name, tool_args, session_id)
                    print(f"  📤 Result: {result[:200]}")
                    yield {"type": "tool_result", "tool_name": tool_name, "result": result}
                    for request in approvals.drain_new():
                        yield {"type": "approval_request", "request": approvals.public(request)}

                    memory.add_tool_call(tool_name, tool_args, result, session_id)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                # Loop again so the model can respond to the tool results
            else:
                done = {"type": "done", "message": full_text or "Done."}
                if deepseek and turn_reasoning:
                    done["reasoning"] = turn_reasoning
                yield done
                return

        yield {"type": "done", "message": full_text or "⚠️ Reached max tool iterations."}


    async def _stream_chat_anthropic(self, user_message: str, session_id: str) -> AsyncGenerator[dict, None]:
        """Claude streaming agentic loop with tool use (Anthropic SDK)."""
        messages = []
        for msg in memory.get_history_for_model(session_id):  # includes the latest user message
            if not msg["content"]:
                continue
            if not messages and msg["role"] != "user":
                continue  # a Claude conversation must open with a user turn
            messages.append({"role": msg["role"], "content": msg["content"]})

        # System prompt and tools stay fixed for the whole turn: changing them mid-loop would
        # invalidate the thinking blocks being replayed (and the prompt cache). A dynamic tool
        # created during this turn becomes available from the next message.
        request = {
            "model": self._model,
            "max_tokens": 64000,
            "system": get_system_prompt(user_message),
            "tools": get_tools_for_anthropic(),
            "messages": messages,
            "cache_control": {"type": "ephemeral"},
        }
        if not self._model.startswith("claude-haiku"):
            request["thinking"] = {"type": "adaptive"}
        if self._model in CLAUDE_FALLBACK_MODELS:
            # If a safety classifier declines, the API re-runs the request on a fallback model.
            request["betas"] = [CLAUDE_FALLBACK_BETA]
            request["fallbacks"] = "default"

        full_text = ""
        json_retries = 0
        iteration = 0

        while iteration < MAX_ITERATIONS:
            iteration += 1

            try:
                async with self._client.beta.messages.stream(**request) as stream:
                    async for event in stream:
                        if event.type == "text":
                            full_text += event.text
                            yield {"type": "chunk", "content": event.text}
                    response = await stream.get_final_message()
                json_retries = 0
            except ValueError:
                # Streamed tool input that isn't parseable JSON; there is no tool_use id to
                # answer, so re-issue the turn (bounded). API errors are not ValueError.
                json_retries += 1
                if json_retries > 2:
                    raise
                continue

            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue

            if response.stop_reason == "refusal":
                note = "\n\n⚠️ Claude declined to continue with this request."
                full_text += note
                yield {"type": "chunk", "content": note}
                break

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if response.stop_reason == "max_tokens":
                note = "\n\n⚠️ The response hit the output limit and was cut off."
                full_text += note
                yield {"type": "chunk", "content": note}
                break  # a truncated tool input parses as a partial object - never run it
            if not tool_uses:
                break

            # Replay the assistant turn unchanged (thinking and fallback blocks included).
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_uses:
                tool_args = dict(block.input) if isinstance(block.input, dict) else {}
                yield {"type": "tool_call", "tool_name": block.name, "tool_args": tool_args}
                print(f"  🔧 Tool call: {block.name}({tool_args})")

                problem = check_tool_args(block.name, block.input)
                if problem:
                    result = f"❌ INVALID_JSON: {problem}. Call the tool again with valid arguments."
                else:
                    result = execute_tool(block.name, tool_args, session_id)
                print(f"  📤 Result: {result[:200]}")
                yield {"type": "tool_result", "tool_name": block.name, "result": result}
                for request_ in approvals.drain_new():
                    yield {"type": "approval_request", "request": approvals.public(request_)}

                memory.add_tool_call(block.name, tool_args, result, session_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result or "(no output)",
                    "is_error": problem is not None,
                })

            # All results for this turn go back in a single user message.
            messages.append({"role": "user", "content": tool_results})
        else:
            yield {"type": "done", "message": full_text or "⚠️ Reached max tool iterations. Here's what I've done so far."}
            return

        yield {"type": "done", "message": full_text or "Done."}


# Global agent instance
agent = MIAAgent()

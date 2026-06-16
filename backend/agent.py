"""
Streaming agent loop.

Yields plain dict events (the router turns them into SSE):
  {"type": "token",       "content": "..."}            partial assistant text
  {"type": "tool_call",   "id","name","args"}          model decided to call a tool
  {"type": "tool_result", "id","name","content"}       tool finished
  {"type": "interrupted"}                               cancelled mid-flight
  {"type": "done",        "content": "<full text>"}     final answer text

Tool calling is a manual loop so we keep full control of streaming + cancellation:
  stream model -> if it asked for tools, run them, append results, loop again.
"""

import asyncio
import re
from typing import AsyncIterator

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from .config import settings
from .tools import TOOLS, TOOLS_BY_NAME

_THINK_OPEN = "<|channel>thought"
_THINK_CLOSE = "<channel|>"


class _ThinkParser:
    """Split a streamed text into 'text' and 'think' segments on the fly."""

    def __init__(self):
        self._buf = ""
        self._in_think = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        self._buf += text
        out: list[tuple[str, str]] = []
        while True:
            tag = _THINK_CLOSE if self._in_think else _THINK_OPEN
            idx = self._buf.find(tag)
            if idx == -1:
                # Hold back enough chars to catch a tag arriving split across chunks.
                safe = max(0, len(self._buf) - len(tag) + 1)
                if safe:
                    out.append(
                        ("think" if self._in_think else "text", self._buf[:safe])
                    )
                    self._buf = self._buf[safe:]
                break
            if idx:
                out.append(("think" if self._in_think else "text", self._buf[:idx]))
            self._buf = self._buf[idx + len(tag) :]
            self._in_think = not self._in_think
        return out

    def flush(self) -> list[tuple[str, str]]:
        result = (
            [("think" if self._in_think else "text", self._buf)] if self._buf else []
        )
        self._buf = ""
        return result


_llm = ChatOpenAI(
    base_url=settings.openai_base_url,
    api_key=settings.openai_api_key,
    model=settings.model_name,
    temperature=0.7,
    streaming=True,
    model_kwargs={"extra_body": {"enable_thinking": True}}
    if settings.enable_thinking
    else {},
)
llm_with_tools = _llm.bind_tools(TOOLS, tool_choice="auto")


async def generate_suggestions(history: list[BaseMessage]) -> list[str]:
    """Return up to 3 likely follow-up questions for the current conversation."""
    prompt = [
        *history,
        HumanMessage(
            content=(
                "Suggest up to 3 short follow-up questions the user might ask next. "
                "Reply with one question per line, no numbering, no bullets, no extra text."
            )
        ),
    ]
    result = await _llm.ainvoke(prompt)
    text = re.sub(
        r"<think>.*?</think>", "", str(result.content), flags=re.DOTALL
    ).strip()
    lines = [
        ln.strip().lstrip("-•1234567890.) ").strip()
        for ln in text.splitlines()
        if ln.strip()
    ]
    return [ln for ln in lines if ln][:3]


async def generate_title(history: list[BaseMessage]) -> str:
    """Ask the LLM for a short conversation title based on the current history."""
    import re

    prompt = [
        *history,
        HumanMessage(
            content=(
                "Summarize this conversation in 5 words or fewer as a title. "
                "Reply with ONLY the title, no punctuation at the end, no quotes."
            )
        ),
    ]
    result = await _llm.ainvoke(prompt)
    text = re.sub(
        r"<think>.*?</think>", "", str(result.content), flags=re.DOTALL
    ).strip()
    return text.strip('"').strip("'")[:120] or "New chat"


async def stream_agent(
    history: list[BaseMessage],
    cancel_event: asyncio.Event,
) -> AsyncIterator[dict]:
    working = list(history)

    while True:
        gathered: AIMessageChunk | None = None
        think_parser = _ThinkParser()

        async for chunk in llm_with_tools.astream(working):
            if cancel_event.is_set():
                yield {"type": "interrupted"}
                return

            # accumulate so tool-call deltas merge into complete tool calls
            gathered = chunk if gathered is None else gathered + chunk

            # Gemma-style thinking: separate field in additional_kwargs.
            thinking_text = chunk.additional_kwargs.get("thinking", "")
            if thinking_text:
                yield {"type": "thinking_token", "content": thinking_text}

            # Pythonic-format tool calls arrive as text content rather than
            # tool_call_chunks, so suppress content while tool_call_chunks are
            # present to avoid leaking raw call syntax to the client.
            if chunk.content and not chunk.tool_call_chunks:
                for kind, text in think_parser.feed(chunk.content):
                    if text:
                        yield {
                            "type": "thinking_token" if kind == "think" else "token",
                            "content": text,
                        }

        for kind, text in think_parser.flush():
            if text:
                yield {
                    "type": "thinking_token" if kind == "think" else "token",
                    "content": text,
                }

        if gathered is None:
            return

        # If the model requested tools, run them and loop back for the final answer.
        if gathered.tool_calls:
            # With the Pythonic parser the tool call text may have streamed as
            # content tokens before we could suppress them; tell the client to
            # discard whatever it accumulated.
            if gathered.content:
                yield {"type": "clear_content"}

            working.append(gathered)
            for tc in gathered.tool_calls:
                yield {
                    "type": "tool_call",
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": tc["args"],
                }
                tool = TOOLS_BY_NAME.get(tc["name"])
                try:
                    result = (
                        tool.invoke(tc["args"])
                        if tool
                        else f"Unknown tool {tc['name']}"
                    )
                except Exception as e:  # noqa: BLE001
                    result = f"Tool error: {e}"
                result = str(result)
                yield {
                    "type": "tool_result",
                    "id": tc["id"],
                    "name": tc["name"],
                    "content": result,
                }
                working.append(ToolMessage(content=result, tool_call_id=tc["id"]))
            continue  # re-enter the loop; model now sees tool results

        # No tools -> this was the final answer.
        yield {"type": "done", "content": gathered.content or ""}
        return

import asyncio
import json
from typing import AsyncIterator

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from .config import settings
from .tools import TOOLS, TOOLS_BY_NAME

_llm = ChatOpenAI(
    base_url=settings.openai_base_url,
    api_key=settings.openai_api_key,
    model=settings.model_name,
    temperature=0.7,
    model_kwargs={"extra_body": {"enable_thinking": True}} if settings.enable_thinking else {},
)

_client = AsyncOpenAI(
    base_url=settings.openai_base_url,
    api_key=settings.openai_api_key,
)

# Tools in OpenAI wire format, derived from LangChain's bind_tools conversion.
_openai_tools: list[dict] = _llm.bind_tools(TOOLS).kwargs.get("tools", [])


async def generate_suggestions(history: list[dict]) -> list[str]:
    prompt = [
        *history,
        {"role": "user", "content": (
            "Suggest up to 3 short follow-up questions the user might ask next. "
            "Reply with one question per line, no numbering, no bullets, no extra text."
        )},
    ]
    result = await _llm.ainvoke(prompt)
    lines = [ln.strip().lstrip("-•1234567890.) ").strip() for ln in str(result.content).splitlines() if ln.strip()]
    return [ln for ln in lines if ln][:3]


async def generate_title(history: list[dict]) -> str:
    prompt = [
        *history,
        {"role": "user", "content": (
            "Summarize this conversation in 5 words or fewer as a title. "
            "Reply with ONLY the title, no punctuation at the end, no quotes."
        )},
    ]
    result = await _llm.ainvoke(prompt)
    return str(result.content).strip().strip('"').strip("'")[:120] or "New chat"


async def stream_agent(
    history: list[dict],
    cancel_event: asyncio.Event,
) -> AsyncIterator[dict]:
    working = list(history)

    while True:
        stream = await _client.chat.completions.create(
            model=settings.model_name,
            messages=working,
            tools=_openai_tools or None,
            tool_choice="auto" if _openai_tools else None,
            stream=True,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}} if settings.enable_thinking else None,
        )

        accumulated_tools: dict[int, dict] = {}
        accumulated_content: list[str] = []
        has_tool_calls = False

        async for chunk in stream:
            if cancel_event.is_set():
                yield {"type": "interrupted"}
                return

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            extra = delta.model_extra or {}
            reasoning = extra.get("reasoning") or extra.get("reasoning_content") or ""
            if reasoning:
                yield {"type": "thinking_token", "content": reasoning}

            if delta.tool_calls:
                has_tool_calls = True
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in accumulated_tools:
                        accumulated_tools[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        accumulated_tools[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            accumulated_tools[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            accumulated_tools[idx]["arguments"] += tc.function.arguments
            elif delta.content:
                accumulated_content.append(delta.content)
                yield {"type": "token", "content": delta.content}

        if has_tool_calls:
            if accumulated_content:
                yield {"type": "clear_content"}

            tool_calls = [
                {
                    "id": accumulated_tools[i]["id"],
                    "name": accumulated_tools[i]["name"],
                    "args": json.loads(accumulated_tools[i]["arguments"] or "{}"),
                }
                for i in sorted(accumulated_tools)
            ]

            working.append({
                "role": "assistant",
                "content": "".join(accumulated_content) or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "args": tc["args"]}
                tool_fn = TOOLS_BY_NAME.get(tc["name"])
                try:
                    result = tool_fn.invoke(tc["args"]) if tool_fn else f"Unknown tool: {tc['name']}"
                except Exception as e:  # noqa: BLE001
                    result = f"Tool error: {e}"
                result = str(result)
                yield {"type": "tool_result", "id": tc["id"], "name": tc["name"], "content": result}
                working.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            continue

        yield {"type": "done", "content": "".join(accumulated_content)}
        return

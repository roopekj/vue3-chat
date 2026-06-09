"""
FastAPI router. Mount with:  app.include_router(chat_router.router)

Endpoints
  GET    /api/conversations                          list conversations
  POST   /api/conversations                          create one
  GET    /api/conversations/{id}/messages            full history
  DELETE /api/conversations/{id}                      delete
  PATCH  /api/conversations/{id}                      rename
  POST   /api/conversations/{id}/messages            send + stream (SSE)
  POST   /api/conversations/{id}/regenerate          re-stream last turn (SSE)
  POST   /api/conversations/{id}/cancel              interrupt active generation
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db
from .agent import stream_agent, generate_title, generate_suggestions

router = APIRouter(prefix="/api")

# conversation_id -> cancel event for the currently running generation.
# NOTE: in-process only. For multi-worker deployments, back this with Redis
# pub/sub (or rely on client disconnect, which is also handled below).
ACTIVE: dict[str, asyncio.Event] = {}


class CreateConversation(BaseModel):
    title: str | None = None


class SendMessage(BaseModel):
    content: str


class RenameConversation(BaseModel):
    title: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ---------- conversation CRUD ----------

@router.get("/conversations")
async def get_conversations():
    return await db.list_conversations()


@router.post("/conversations")
async def post_conversation(body: CreateConversation):
    return await db.create_conversation(body.title or "New chat")


@router.get("/conversations/{conv_id}/messages")
async def get_history(conv_id: str):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    return await db.get_messages(conv_id)


@router.delete("/conversations/{conv_id}")
async def remove_conversation(conv_id: str):
    await db.delete_conversation(conv_id)
    return {"ok": True}


@router.patch("/conversations/{conv_id}")
async def patch_conversation(conv_id: str, body: RenameConversation):
    await db.rename_conversation(conv_id, body.title)
    return {"ok": True}


@router.post("/conversations/{conv_id}/suggestions")
async def get_suggestions(conv_id: str):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    history = await db.get_lc_history(conv_id)
    return {"suggestions": await generate_suggestions(history)}


@router.post("/conversations/{conv_id}/cancel")
async def cancel(conv_id: str):
    ev = ACTIVE.get(conv_id)
    if ev:
        ev.set()
    return {"ok": True, "cancelled": ev is not None}


# ---------- generation (shared by send + regenerate) ----------

async def _generate_stream(conv_id: str, request: Request) -> StreamingResponse:
    history = await db.get_lc_history(conv_id)

    cancel_event = asyncio.Event()
    ACTIVE[conv_id] = cancel_event

    async def event_stream():
        parts: list[str] = []
        thinking_parts: list[str] = []
        tool_steps: list[dict] = []
        interrupted = False
        try:
            async for ev in stream_agent(history, cancel_event):
                # client closed the tab / aborted fetch -> stop
                if await request.is_disconnected():
                    cancel_event.set()

                if ev["type"] == "token":
                    parts.append(ev["content"])
                elif ev["type"] == "thinking_token":
                    thinking_parts.append(ev["content"])
                elif ev["type"] == "tool_call":
                    tool_steps.append({"id": ev["id"], "name": ev["name"],
                                       "args": ev["args"], "result": None})
                elif ev["type"] == "tool_result":
                    for st in tool_steps:
                        if st["id"] == ev["id"]:
                            st["result"] = ev["content"]
                elif ev["type"] == "interrupted":
                    interrupted = True

                yield _sse(ev)
        except asyncio.CancelledError:
            interrupted = True
            raise
        finally:
            text = "".join(parts)
            thinking = "".join(thinking_parts)
            # persist whatever we produced (including partial text on interrupt)
            if text.strip() or tool_steps:
                saved = await db.add_message(
                    conv_id, "assistant", text,
                    extra={"tools": tool_steps, "interrupted": interrupted, "thinking": thinking},
                )
                yield _sse({"type": "saved", "message_id": saved["id"],
                            "interrupted": interrupted})
                title = await generate_title(await db.get_lc_history(conv_id))
                await db.rename_conversation(conv_id, title)
                yield _sse({"type": "title", "title": title})
            ACTIVE.pop(conv_id, None)
            yield _sse({"type": "end"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: SendMessage, request: Request):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    await db.add_message(conv_id, "user", body.content)
    return await _generate_stream(conv_id, request)


@router.post("/conversations/{conv_id}/regenerate")
async def regenerate(conv_id: str, request: Request):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    # drop the previous assistant answer(s); history now ends on the user turn
    await db.delete_trailing_assistant(conv_id)
    return await _generate_stream(conv_id, request)

"""
FastAPI router. Mount with:  app.include_router(chat_router.router)

Endpoints
  GET    /api/conversations                          list conversations
  POST   /api/conversations                          create one
  GET    /api/conversations/{id}/messages            full history
  DELETE /api/conversations/{id}                      delete
  PATCH  /api/conversations/{id}                      rename
  POST   /api/conversations/{id}/messages            send message (kicks off background generation)
  POST   /api/conversations/{id}/regenerate          re-generate last turn (background)
  POST   /api/conversations/{id}/cancel              interrupt active generation
  WS     /api/ws                                     streaming events for all conversations
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import db
from .agent import stream_agent, generate_title, generate_suggestions

router = APIRouter(prefix="/api")

# conversation_id -> cancel event for the currently running generation.
ACTIVE: dict[str, asyncio.Event] = {}

# Queue for the single connected WebSocket client.
_ws_queue: asyncio.Queue | None = None


async def _ws_publish(event: dict) -> None:
    if _ws_queue is not None:
        await _ws_queue.put(event)


class CreateConversation(BaseModel):
    title: str | None = None


class SendMessage(BaseModel):
    content: str


class RenameConversation(BaseModel):
    title: str


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


# ---------- WebSocket ----------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _ws_queue
    await websocket.accept()
    _ws_queue = asyncio.Queue()

    async def _sender():
        while True:
            event = await _ws_queue.get()
            if event is None:
                break
            try:
                await websocket.send_json(event)
            except Exception:
                break

    sender_task = asyncio.create_task(_sender())
    try:
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "cancel":
                    ev = ACTIVE.get(msg.get("conv_id"))
                    if ev:
                        ev.set()
            except WebSocketDisconnect:
                break
    finally:
        _ws_queue.put_nowait(None)
        _ws_queue = None
        await sender_task
        # Cancel any in-progress generations when the client disconnects.
        for ev in list(ACTIVE.values()):
            ev.set()


# ---------- generation ----------

async def _generate_background(conv_id: str) -> None:
    history = await db.get_lc_history(conv_id)
    cancel_event = asyncio.Event()
    ACTIVE[conv_id] = cancel_event

    parts: list[str] = []
    thinking_parts: list[str] = []
    tool_steps: list[dict] = []
    interrupted = False

    try:
        async for ev in stream_agent(history, cancel_event):
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
            await _ws_publish({**ev, "conv_id": conv_id})
    except asyncio.CancelledError:
        interrupted = True
    finally:
        text = "".join(parts)
        thinking = "".join(thinking_parts)
        if text.strip() or tool_steps:
            saved = await db.add_message(
                conv_id, "assistant", text,
                extra={"tools": tool_steps, "interrupted": interrupted, "thinking": thinking},
            )
            await _ws_publish({"type": "saved", "conv_id": conv_id,
                                "message_id": saved["id"], "interrupted": interrupted})
            title = await generate_title(await db.get_lc_history(conv_id))
            await db.rename_conversation(conv_id, title)
            await _ws_publish({"type": "title", "conv_id": conv_id, "title": title})
        ACTIVE.pop(conv_id, None)
        await _ws_publish({"type": "end", "conv_id": conv_id})


@router.post("/conversations/{conv_id}/messages")
async def send_message(conv_id: str, body: SendMessage):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    await db.add_message(conv_id, "user", body.content)
    asyncio.create_task(_generate_background(conv_id))
    return {"ok": True}


@router.post("/conversations/{conv_id}/regenerate")
async def regenerate(conv_id: str):
    if not await db.conversation_exists(conv_id):
        raise HTTPException(404, "conversation not found")
    await db.delete_trailing_assistant(conv_id)
    asyncio.create_task(_generate_background(conv_id))
    return {"ok": True}

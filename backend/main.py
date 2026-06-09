"""Example app wiring. Fold this into your existing FastAPI app instead if you have one."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from . import chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()  # creates ui_conversations / ui_messages if missing
    yield


app = FastAPI(lifespan=lifespan)

# adjust to your Vue dev server origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)

# run:  uvicorn backend.main:app --reload --port 8080

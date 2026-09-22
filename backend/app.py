"""FastAPI app cho tro ly noi quy HUST (RAG chatbot)."""

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from backend import config
from backend.indexer import ensure_index
from backend.rag import answer_question


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Free-tier host khong co persistent disk -> ChromaDB co the trong sau moi
    # lan deploy/restart. Tu dong build lai tu data/raw/ da commit san neu can.
    ensure_index()
    yield


app = FastAPI(title="HUST Noi Quy RAG Chatbot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 20  # 20 cap user+assistant = 40 message

# ---------- Rate limit don gian theo IP (chong lam dung API tra phi) ----------
# In-memory, phu hop 1 instance/1 worker (dung cho free-tier). Neu scale nhieu
# worker/instance can chuyen sang store dung chung (vd Redis).
_rate_limit_hits: dict[str, deque] = defaultdict(deque)


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    hits = _rate_limit_hits[client_ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="Ban gui qua nhieu yeu cau, vui long thu lai sau it phut.",
        )
    hits.append(now)


class ChatMessage(BaseModel):
    role: str
    content: str = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError("role phai la 'user' hoac 'assistant'")
        return v


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatMessage] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS * 2)

    @field_validator("history")
    @classmethod
    def history_must_alternate(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        # Chan client gia mao nhieu luot "assistant" lien tiep de danh lua model.
        for i, msg in enumerate(v):
            expected_role = "user" if i % 2 == 0 else "assistant"
            if msg.role != expected_role:
                raise ValueError(
                    "history phai xen ke user/assistant, bat dau bang user"
                )
        return v


class Source(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Cau hoi khong duoc de trong.")
    # Render/hau het PaaS dat sau reverse proxy - IP that nam o X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown"
    )
    _check_rate_limit(client_ip)
    try:
        history = [m.model_dump() for m in req.history]
        result = answer_question(req.message, history=history)
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi xu ly: {e}")


@app.get("/api/health")
def health():
    return {"status": "ok", "model": config.CLAUDE_MODEL}


# Phuc vu frontend tinh (HTML/CSS/JS) tu thu muc frontend/
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


def _http_detail(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        parts = [_http_detail(x) if isinstance(x, BaseException) else str(x) for x in exc.exceptions]
        return "MCP / TaskGroup: " + " | ".join(parts)
    return f"{type(exc).__name__}: {exc}"

from . import db
from .agent import run_chat
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="Web Pentest Agent MVP", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "mcp_enabled": settings.mcp_enabled,
        "has_openai_key": bool(settings.openai_api_key),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    try:
        reply, sid = await run_chat(body.message.strip(), body.session_id)
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        raise HTTPException(status_code=500, detail=_http_detail(e)) from e
    return ChatResponse(reply=reply, session_id=sid)


@app.get("/api/history")
async def history(limit: int = 200):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 1..500")
    return await db.list_history(limit=limit)


@app.delete("/api/history")
async def delete_history():
    try:
        await db.clear_history()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_http_detail(e))


# ── WSTG Status ──────────────────────────────────────────────

class WstgStatusUpdate(BaseModel):
    wstg_id: str
    status: str  # "not_started" | "pass" | "issue"
    target_url: str | None = None
    result_summary: str | None = None


@app.get("/api/wstg-status")
async def get_wstg_status():
    return await db.get_wstg_results()


@app.put("/api/wstg-status")
async def update_wstg_status(body: WstgStatusUpdate):
    try:
        await db.upsert_wstg_result(
            wstg_id=body.wstg_id,
            status=body.status,
            target_url=body.target_url,
            result_summary=body.result_summary,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_http_detail(e))

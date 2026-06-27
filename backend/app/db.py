import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from .config import settings
import httpx
import warnings

# Tắt kiểm tra SSL toàn cục cho httpx (Fix lỗi CERTIFICATE_VERIFY_FAILED)
original_client_init = httpx.Client.__init__
def new_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_client_init(self, *args, **kwargs)
httpx.Client.__init__ = new_client_init

original_async_client_init = httpx.AsyncClient.__init__
def new_async_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_async_client_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = new_async_client_init

_supabase: Any = None


def _client():
    global _supabase
    if _supabase is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError(
                "Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY trong .env — "
                "xem backend/supabase_schema.sql để tạo bảng."
            )
        from supabase import create_client

        _supabase = create_client(
            settings.supabase_url.strip(),
            settings.supabase_service_role_key.strip(),
        )
    return _supabase


def _insert_row(row: dict) -> None:
    _client().table("command_log").insert(row).execute()


def _select_history(limit: int) -> list[dict]:
    res = (
        _client()
        .table("command_log")
        .select("id, created_at, session_id, role, content, tool_name, tool_args, tool_result, meta")
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return list(res.data or [])

def _select_history_by_session(session_id: str, limit: int) -> list[dict]:
    res = (
        _client()
        .table("command_log")
        .select("id, created_at, session_id, role, content, tool_name, tool_args, tool_result, meta, wstg_id")
        .eq("session_id", session_id)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )
    return list(res.data or [])


def _ping_table() -> None:
    _client().table("command_log").select("id").limit(1).execute()


async def init_db() -> None:
    """Kiểm tra kết nối Supabase và tồn tại bảng (tạo bảng trong SQL Editor của Supabase)."""
    await asyncio.to_thread(_ping_table)


async def log_entry(
    *,
    role: str,
    content: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result: str | None = None,
    wstg_id: str | None = None,
    meta: dict | None = None,
) -> None:
    created = datetime.now(timezone.utc).isoformat()
    row = {
        "created_at": created,
        "session_id": session_id,
        "role": role,
        "content": content,
        "tool_name": tool_name,
        "tool_args": json.dumps(tool_args, ensure_ascii=False) if tool_args is not None else None,
        "tool_result": tool_result,
        "wstg_id": wstg_id,
        "meta": json.dumps(meta, ensure_ascii=False) if meta is not None else None,
    }
    await asyncio.to_thread(_insert_row, row)


async def list_history(limit: int = 200) -> list[dict]:
    return await asyncio.to_thread(_select_history, limit)

async def list_history_by_session(session_id: str, limit: int = 200) -> list[dict]:
    return await asyncio.to_thread(_select_history_by_session, session_id, limit)


def _clear_history() -> None:
    _client().table("command_log").delete().gt("id", -1).execute()


async def clear_history() -> None:
    await asyncio.to_thread(_clear_history)


def _list_wstg_logs(wstg_id: str, session_id: str | None = None) -> list[dict]:
    query = _client().table("command_log").select("*").eq("wstg_id", wstg_id)
    if session_id:
        query = query.eq("session_id", session_id)
    res = query.order("id").execute()
    return list(res.data or [])


async def list_wstg_logs(wstg_id: str, session_id: str | None = None) -> list[dict]:
    """Lấy danh sách các tool đã chạy cho một mục WSTG cụ thể"""
    return await asyncio.to_thread(_list_wstg_logs, wstg_id, session_id)


# ── WSTG Results ──────────────────────────────────────────────

def _get_wstg_results() -> list[dict]:
    res = (
        _client()
        .table("wstg_results")
        .select("*")
        .order("wstg_id")
        .execute()
    )
    return list(res.data or [])


def _upsert_wstg_result(row: dict) -> None:
    _client().table("wstg_results").upsert(row, on_conflict="wstg_id").execute()


async def get_wstg_results() -> list[dict]:
    return await asyncio.to_thread(_get_wstg_results)


async def upsert_wstg_result(
    *,
    wstg_id: str,
    status: str,
    target_url: str | None = None,
    result_summary: str | None = None,
) -> None:
    row = {
        "wstg_id": wstg_id,
        "status": status,
        "target_url": target_url,
        "result_summary": result_summary[:4000] if result_summary else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await asyncio.to_thread(_upsert_wstg_result, row)


# ── RAG Knowledge Search ──────────────────────────────────────

def _search_wstg_kb(query_embedding: list[float], match_threshold: float, match_count: int) -> list[dict]:
    # Gọi RPC đã định nghĩa trên Supabase
    res = _client().rpc(
        "match_wstg_kb",
        {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": match_count
        }
    ).execute()
    return list(res.data or [])

async def search_wstg_kb(query_embedding: list[float], match_threshold: float = 0.5, match_count: int = 2) -> list[dict]:
    """Tìm kiếm nội dung WSTG test case dựa trên vector ngữ nghĩa"""
    return await asyncio.to_thread(_search_wstg_kb, query_embedding, match_threshold, match_count)

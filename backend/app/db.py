import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from .config import settings

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
        "meta": json.dumps(meta, ensure_ascii=False) if meta is not None else None,
    }
    await asyncio.to_thread(_insert_row, row)


async def list_history(limit: int = 200) -> list[dict]:
    return await asyncio.to_thread(_select_history, limit)


def _clear_history() -> None:
    _client().table("command_log").delete().gt("id", -1).execute()


async def clear_history() -> None:
    await asyncio.to_thread(_clear_history)

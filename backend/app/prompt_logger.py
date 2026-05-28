"""
Prompt Logger — Ghi lại toàn bộ prompt gửi lên LLM cho mỗi mục WSTG.
Giúp debug, phân tích, và tạo báo cáo chi tiết.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)


def _sanitize_filename(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")


def log_prompt(
    *,
    wstg_id: str | None = None,
    session_id: str | None = None,
    system_prompt: str,
    user_message: str,
    rag_context: str | None = None,
    endpoint_hints: str | None = None,
    chain_of_evidence: str | None = None,
    recon_cache_data: str | None = None,
    cross_vuln_alerts: str | None = None,
    tools_available: list[str] | None = None,
    round_num: int = 0,
    direction: str = "TO_LLM",  # TO_LLM hoặc FROM_LLM
    content: str | None = None,
) -> None:
    """Ghi log prompt vào file JSON cho phân tích sau này."""
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "timestamp": timestamp,
        "direction": direction,
        "wstg_id": wstg_id,
        "session_id": session_id,
        "round_num": round_num,
        "system_prompt_length": len(system_prompt) if system_prompt else 0,
        "user_message_length": len(user_message) if user_message else 0,
        "rag_context_length": len(rag_context) if rag_context else 0,
        "endpoint_hints_length": len(endpoint_hints) if endpoint_hints else 0,
        "chain_of_evidence_length": len(chain_of_evidence) if chain_of_evidence else 0,
        "recon_cache_length": len(recon_cache_data) if recon_cache_data else 0,
        "cross_vuln_alerts_length": len(cross_vuln_alerts) if cross_vuln_alerts else 0,
        "tools_count": len(tools_available) if tools_available else 0,
    }

    # File chi tiết — ghi đầy đủ nội dung prompt
    detail_entry = {
        **log_entry,
        "system_prompt": system_prompt,
        "user_message": user_message,
        "rag_context": rag_context,
        "endpoint_hints": endpoint_hints,
        "chain_of_evidence": chain_of_evidence,
        "recon_cache_data": recon_cache_data,
        "cross_vuln_alerts": cross_vuln_alerts,
        "tools_available": tools_available,
        "content": content,
    }

    # Ghi vào file tổng
    summary_file = _LOG_DIR / "prompt_log_summary.jsonl"
    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # Ghi vào file chi tiết theo wstg_id
    if wstg_id:
        detail_file = _LOG_DIR / f"prompt_{_sanitize_filename(wstg_id)}.jsonl"
        with open(detail_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(detail_entry, ensure_ascii=False) + "\n")

    # Ghi vào file session
    if session_id:
        session_file = _LOG_DIR / f"session_{_sanitize_filename(session_id)}.jsonl"
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(detail_entry, ensure_ascii=False) + "\n")

    print(f"[PROMPT_LOG] {direction} | {wstg_id or 'chat'} | round={round_num} | sys={log_entry['system_prompt_length']}c | user={log_entry['user_message_length']}c | rag={log_entry['rag_context_length']}c | recon={log_entry['recon_cache_length']}c | evidence={log_entry['chain_of_evidence_length']}c")


def log_tool_call(
    *,
    wstg_id: str | None = None,
    session_id: str | None = None,
    round_num: int,
    tool_name: str,
    tool_args: dict,
    tool_result_preview: str,
) -> None:
    """Ghi log tool call riêng biệt."""
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "type": "TOOL_CALL",
        "wstg_id": wstg_id,
        "session_id": session_id,
        "round_num": round_num,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_result_preview": tool_result_preview[:500],
    }
    
    tool_file = _LOG_DIR / "tool_calls.jsonl"
    with open(tool_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[TOOL_LOG] {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:100]}) → {len(tool_result_preview)}c")


def log_llm_response(
    *,
    wstg_id: str | None = None,
    session_id: str | None = None,
    round_num: int,
    has_tool_calls: bool,
    tool_call_names: list[str] | None = None,
    text_content_preview: str | None = None,
    conclusion: str | None = None,
) -> None:
    """Ghi log phản hồi từ LLM."""
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "type": "LLM_RESPONSE",
        "wstg_id": wstg_id,
        "session_id": session_id,
        "round_num": round_num,
        "has_tool_calls": has_tool_calls,
        "tool_call_names": tool_call_names,
        "text_preview": (text_content_preview or "")[:300],
        "conclusion": conclusion,
    }

    response_file = _LOG_DIR / "llm_responses.jsonl"
    with open(response_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def clear_logs() -> None:
    """Xóa toàn bộ log cũ."""
    for f in _LOG_DIR.glob("*.jsonl"):
        f.unlink()
    print("[PROMPT_LOG] Đã xóa toàn bộ log cũ.")


def get_prompt_summary(wstg_id: str) -> dict:
    """Đọc tóm tắt prompt cho 1 WSTG ID cụ thể."""
    detail_file = _LOG_DIR / f"prompt_{_sanitize_filename(wstg_id)}.jsonl"
    if not detail_file.exists():
        return {"wstg_id": wstg_id, "entries": []}
    
    entries = []
    with open(detail_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    return {"wstg_id": wstg_id, "entries": entries}

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
    wstg_id: str | None = None


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
        reply, sid = await run_chat(
            body.message.strip(),
            body.session_id,
            wstg_id=body.wstg_id
        )

        # --- NEW: Tự động tách kết luận và cập nhật WSTG Status ---
        if body.wstg_id:
            import re
            status_match = re.search(r"\[CONCLUSION\][^\w]*(PASS|ISSUE|NEEDS_REVIEW)", reply, re.IGNORECASE)
            summary_match = re.search(r"\[SUMMARY\][^\w]*(.*)", reply, re.DOTALL | re.IGNORECASE)
            
            if status_match:
                new_status = status_match.group(1).lower()
                new_summary = summary_match.group(1).strip() if summary_match else "Agent đã đưa ra kết luận nhưng thiếu tóm tắt."
                
                await db.upsert_wstg_result(
                    wstg_id=body.wstg_id,
                    status=new_status,
                    result_summary=new_summary
                )
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


@app.get("/api/wstg-logs")
async def get_wstg_logs(wstg_id: str, session_id: str | None = None):
    """API lấy lịch sử chạy tool chi tiết cho từng mục WSTG"""
    try:
        return await db.list_wstg_logs(wstg_id, session_id or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_http_detail(e))


# ── Prompt Logs ──────────────────────────────────────────────

@app.get("/api/prompt-logs")
async def get_prompt_logs(wstg_id: str | None = None):
    """API xem prompt log cho debugging và báo cáo"""
    from .prompt_logger import get_prompt_summary
    from pathlib import Path
    import json
    
    log_dir = settings.backend_root / "logs"
    
    if wstg_id:
        return get_prompt_summary(wstg_id)
    
    # Trả về summary tổng
    summary_file = log_dir / "prompt_log_summary.jsonl"
    if not summary_file.exists():
        return {"entries": [], "message": "Chưa có prompt log. Hãy chạy ít nhất 1 test case."}
    
    entries = []
    with open(summary_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    return {"entries": entries[-100:], "total": len(entries)}


@app.get("/api/run-all-report")
async def get_run_all_report():
    """API lấy báo cáo Run All Tests từ Database (cập nhật theo thời gian thực)"""
    from datetime import datetime
    
    # 1. Fetch từ DB (chứa toàn bộ kết quả đã chạy)
    results = await db.get_wstg_results()
    
    if not results:
        return {"data": None, "report_md": "Ch\u01b0a c\u00f3 k\u1ebft qu\u1ea3 test n\u00e0o trong Database. H\u00e3y b\u1eaft \u0111\u1ea7u ch\u1ea1y test!"}

    # 2. Xây dựng Markdown ĐỘNG (REAL-TIME)
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    issues = sum(1 for r in results if r["status"] == "issue")
    needs_review = sum(1 for r in results if r["status"] == "needs_review")
    errors = sum(1 for r in results if r["status"] == "error")
    
    target_url = next((r["target_url"] for r in results if r.get("target_url")), "N/A")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# BAO CAO KIEM THU OWASP WSTG (CAP NHAT LIEN TUC)",
        f"",
        f"## Thong tin chung",
        f"| Muc | Gia tri |",
        f"|-----|---------|",
        f"| **Muc tieu** | `{target_url}` |",
        f"| **Thoi diem tao** | {now_str} |",
        f"| **So test da chay** | {total} / 105 |",
        f"",
        f"## Tong ket",
        f"| Trang thai | So luong | Ty le |",
        f"|------------|----------|-------|",
        f"| [PASS] | {passed} | {passed/total*100:.1f}% |" if total > 0 else "",
        f"| [ISSUE] | {issues} | {issues/total*100:.1f}% |" if total > 0 else "",
        f"| [NEEDS_REVIEW] | {needs_review} | {needs_review/total*100:.1f}% |" if total > 0 else "",
        f"| [ERROR] | {errors} | {errors/total*100:.1f}% |" if total > 0 else "",
        f"| **TONG** | **{total}** | **100%** |",
        f"",
        f"---",
        f"",
    ]
    
    # Nhóm theo category
    categories = {}
    for r in sorted(results, key=lambda x: x["wstg_id"]):
        cat = r["wstg_id"].split("-")[1] if "-" in r["wstg_id"] else "OTHER"
        if cat not in categories: categories[cat] = []
        categories[cat].append(r)
        
    cat_names = {
        "INFO": "1. Information Gathering", "CONF": "2. Configuration and Deploy",
        "IDNT": "3. Identity Management", "ATHN": "4. Authentication",
        "ATHZ": "5. Authorization", "SESS": "6. Session Management",
        "INPV": "7. Data Validation (Input)", "ERRH": "8. Error Handling",
        "CRYP": "9. Cryptography", "BUSL": "10. Business Logic",
        "CLNT": "11. Client-Side", "APIT": "12. API Testing",
    }
    
    for cat_code, cat_tests in categories.items():
        cat_name = cat_names.get(cat_code, cat_code)
        cat_passed = sum(1 for t in cat_tests if t["status"] == "pass")
        cat_issues = sum(1 for t in cat_tests if t["status"] == "issue")
        
        lines.append(f"## {cat_name}")
        lines.append(f"**Ket qua: {cat_passed} PASS / {cat_issues} ISSUE / {len(cat_tests)} tong**")
        lines.append(f"")
        
        for result in cat_tests:
            wstg_id = result["wstg_id"]
            status = result["status"]
            icon = {"pass": "[PASS]", "issue": "[ISSUE]", "needs_review": "[REVIEW]", "error": "[ERROR]"}.get(status, "[?]")
            summary = result.get("result_summary") or "Chua co chi tiet."
            
            lines.append(f"### {wstg_id} - {icon} {status.upper()}")
            lines.append(summary)
            lines.append(f"")
            lines.append(f"---")
        lines.append(f"")
        
    # Chi tiết các Issues
    issue_tests = [r for r in results if r["status"] == "issue"]
    if issue_tests:
        lines.append(f"## CHI TIET CAC LO HONG TIM THAY (ISSUE)")
        lines.append(f"")
        for result in issue_tests:
            lines.append(f"### {result['wstg_id']}")
            lines.append(f"{result.get('result_summary', 'Khong co chi tiet.')}")
            lines.append(f"")
            lines.append(f"---")

    report_md = "\n".join(lines)
    
    return {
        "data": results,
        "report_md": report_md
    }


@app.get("/api/key-pool-status")
async def key_pool_status():
    """API xem trạng thái API key pool"""
    from .config import api_key_pool
    return api_key_pool.status()


@app.get("/api/recon-cache")
async def get_recon_cache():
    """API xem trạng thái Shared Recon Cache"""
    from .recon_cache import cache_status, get_recon_summary
    status = cache_status()
    status["summary_preview"] = get_recon_summary() or "(trống)"
    return status


@app.delete("/api/recon-cache")
async def clear_recon_cache():
    """API xóa Recon Cache (dùng khi đổi target hoặc reset)"""
    from .recon_cache import clear_cache
    clear_cache()
    return {"ok": True, "message": "Recon cache đã được xóa."}


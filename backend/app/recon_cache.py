"""
Shared Recon Cache - Chia sẻ kết quả trinh sát giữa các test WSTG.

Khi test A chạy nmap/dirb/whatweb → kết quả được lưu vào cache.
Khi test B bắt đầu → nhận sẵn dữ liệu trinh sát mà không cần chạy lại.

Quy tắc:
- Mỗi tool_key (ví dụ: "nmap_scan", "dirb_web_scan") chỉ lưu 1 lần duy nhất.
- Nếu đã có trong cache → SKIP, không ghi đè.
- Lần này chúng ta lưu cả full_result để có thể intercept call thực tế.
- Cache lưu trên disk dưới dạng JSON → persist qua restart.
"""

import json
import re
import threading
from pathlib import Path
from typing import Optional

# Các tool recon cần cache kết quả
RECON_TOOLS = {
    "nmap_scan",
    "nmap_scan_ports",   # Tên MCP tool thực tế
    "dirb_web_scan",
    "whatweb_fingerprint",
    "nikto_web_scan",
}

# Mapping tên MCP tool → tên cache key chuẩn hóa
_TOOL_NAME_MAP = {
    "nmap_scan_ports": "nmap_scan",  # MCP đăng ký là nmap_scan_ports
}

# Các URL quan trọng cần cache kết quả curl để đưa vào prompt summary
IMPORTANT_URLS = {
    "/robots.txt", "/ftp/", "/api/Users/", "/api/Products/",
    "/api/Feedbacks", "/rest/user/login", "/administration",
    "/rest/products/search", "/.env", "/.git/",
}

CACHE_FILE = Path(__file__).parent.parent / "recon_cache.json"
MAX_SUMMARY_LENGTH = 2500  # Giới hạn inject vào prompt
_cache_lock = threading.Lock()  # Thread safety cho concurrent requests


from .knowledge_graph import DynamicKnowledgeGraph

_dkg = DynamicKnowledgeGraph(CACHE_FILE)

def _get_target_from_args(tool_args: dict) -> str:
    """Trích xuất target host từ tool_args."""
    url = tool_args.get("url", tool_args.get("target", ""))
    if url:
        import re as _re
        m = _re.match(r"https?://([^/]+)", url)
        if m:
            return m.group(1)
    return "localhost:3000"

def _extract_nmap_summary(result: str) -> str:
    lines = result.split("\n")
    important = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if any(kw in line.lower() for kw in ["open", "filtered", "os details", "service info", "running:", "aggressive os"]):
            important.append(line)
    return "\n".join(important[:20]) if important else result[:500]

def _extract_dirb_summary(result: str) -> str:
    urls = re.findall(r"(?:DIRECTORY|==> )?\s*(https?://[^\s]+)", result)
    if urls:
        paths = []
        for url in urls:
            path = re.sub(r"https?://[^/]+", "", url)
            if path and path not in paths: paths.append(path)
        return "Paths phát hiện: " + ", ".join(paths[:30])
    return result[:500]

def _extract_whatweb_summary(result: str) -> str:
    return result[:600]

def _extract_curl_summary(result: str) -> str:
    lines = result.split("\n")
    important = []
    for line in lines[:30]:
        line = line.strip()
        if not line: continue
        if any(kw in line.lower() for kw in ["http/", "status", "content-type", "server:", "x-powered-by", "set-cookie", "location:", "access-control", "x-frame"]):
            important.append(line)
    body_preview = result[:300] if len(result) < 500 else ""
    summary = "\n".join(important[:15])
    if body_preview and not summary:
        summary = body_preview
    return summary or result[:400]

def save_recon(tool_name: str, tool_args: dict, tool_result: str) -> bool:
    """
    Lưu kết quả recon vào cache (lưu cả summary và full_result).
    Tích hợp DKG để parse thành node/edge.
    """
    # Xử lý các tool recon chính
    if tool_name in RECON_TOOLS:
        cache_key = _TOOL_NAME_MAP.get(tool_name, tool_name)
        
        if cache_key == "nmap_scan":
            summary = _extract_nmap_summary(tool_result)
            _dkg.ingest_nmap(tool_result, _get_target_from_args(tool_args))
        elif cache_key == "dirb_web_scan":
            summary = _extract_dirb_summary(tool_result)
            _dkg.ingest_dirb(tool_result, _get_target_from_args(tool_args))
        elif cache_key == "whatweb_fingerprint":
            summary = _extract_whatweb_summary(tool_result)
            _dkg.ingest_whatweb(tool_result, _get_target_from_args(tool_args))
        else:
            summary = tool_result[:500]
        
        data = {
            "tool": tool_name,
            "args": tool_args,
            "summary": summary,
            "full_result": tool_result,
            "source": "auto",
        }
        
        saved = _dkg.save_legacy(cache_key, data)
        if saved:
            _dkg.save()
            print(f"[RECON CACHE] Saved: {cache_key} ← {tool_name} ({len(summary)} chars)")
        return saved
    
    # Xử lý curl cho TẤT CẢ url (để chặn lệnh chạy lại)
    if tool_name == "curl_http_check":
        url = tool_args.get("url", "")
        method = tool_args.get("method", "GET")
        path = re.sub(r"https?://[^/]+", "", url)
        if not path: path = "/"
        cache_key = f"curl:{method}:{path}"
        
        # DKG Ingest
        _dkg.ingest_curl(tool_result, url, method)
        
        # Check quan trọng để làm summary
        is_imp = False
        summary = ""
        for imp_url in IMPORTANT_URLS:
            if imp_url.lower() in path.lower():
                is_imp = True
                summary = _extract_curl_summary(tool_result)
                break
                
        data = {
            "tool": tool_name,
            "method": method,
            "path": path,
            "summary": summary,
            "full_result": tool_result,
            "is_important": is_imp,
            "source": "auto",
        }
        saved = _dkg.save_legacy(cache_key, data)
        if saved:
            _dkg.save()
            if is_imp:
                print(f"[RECON CACHE] Saved IMPORTANT curl: {method} {path}")
        return saved
        
    return False
def get_cached_tool_result(tool_name: str, tool_args: dict) -> Optional[str]:
    """
    Trả về full_result nếu tool đã được cache, giúp intercept tool call.
    """
    return _dkg.get_cached_tool_result(tool_name, tool_args)

def get_recon_summary() -> Optional[str]:
    """
    Tạo chuỗi tóm tắt recon để inject vào prompt.
    Chỉ inject các thông tin quan trọng.
    """
    return _dkg.generate_context_summary()

def clear_cache() -> None:
    """Xóa toàn bộ cache (dùng khi đổi target hoặc reset)."""
    global _dkg
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    _dkg = DynamicKnowledgeGraph(CACHE_FILE)  # Fresh instance
    print("[RECON CACHE] Cleared.")

def cache_status() -> dict:
    """Trả về trạng thái cache hiện tại."""
    return {
        "nodes_count": len(_dkg._nodes),
        "edges_count": len(_dkg._edges),
        "legacy_entries": len(_dkg._legacy_cache),
        "cache_file": str(CACHE_FILE),
    }

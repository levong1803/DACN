"""
Shared Recon Cache - Chia sẻ kết quả trinh sát giữa các test WSTG.

Khi test A chạy nmap/dirb/whatweb → kết quả được lưu vào cache.
Khi test B bắt đầu → nhận sẵn dữ liệu trinh sát mà không cần chạy lại.

Quy tắc:
- Mỗi tool_key (ví dụ: "nmap_scan", "dirb_web_scan") chỉ lưu 1 lần duy nhất.
- Nếu đã có trong cache → SKIP, không ghi đè.
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
    "nmap_scan_ports",   # Tên MCP tool thực tế (fix bug: trước đây bị miss)
    "dirb_web_scan",
    "whatweb_fingerprint",
    "nikto_web_scan",
}

# Mapping tên MCP tool → tên cache key chuẩn hóa
_TOOL_NAME_MAP = {
    "nmap_scan_ports": "nmap_scan",  # MCP đăng ký là nmap_scan_ports
}

# Các URL quan trọng cần cache kết quả curl
IMPORTANT_URLS = {
    "/robots.txt", "/ftp/", "/api/Users/", "/api/Products/",
    "/api/Feedbacks", "/rest/user/login", "/administration",
    "/rest/products/search", "/.env", "/.git/",
}

CACHE_FILE = Path(__file__).parent.parent / "recon_cache.json"
MAX_SUMMARY_LENGTH = 2500  # Giới hạn inject vào prompt
_cache_lock = threading.Lock()  # Thread safety cho concurrent requests


def _load_cache() -> dict:
    """Đọc cache từ disk (thread-safe)."""
    with _cache_lock:
        if CACHE_FILE.exists():
            try:
                return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}


def _save_cache(cache: dict) -> None:
    """Ghi cache xuống disk (thread-safe)."""
    with _cache_lock:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_nmap_summary(result: str) -> str:
    """Trích xuất thông tin quan trọng từ kết quả nmap."""
    lines = result.split("\n")
    important = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Giữ lại: open ports, OS detection, service info
        if any(kw in line.lower() for kw in ["open", "filtered", "os details", "service info", "running:", "aggressive os"]):
            important.append(line)
    return "\n".join(important[:20]) if important else result[:500]


def _extract_dirb_summary(result: str) -> str:
    """Trích xuất danh sách paths từ kết quả dirb."""
    # Tìm các URL được phát hiện
    urls = re.findall(r"(?:DIRECTORY|==> )?\s*(https?://[^\s]+)", result)
    if urls:
        # Chỉ giữ path phần sau domain
        paths = []
        for url in urls:
            path = re.sub(r"https?://[^/]+", "", url)
            if path and path not in paths:
                paths.append(path)
        return "Paths phát hiện: " + ", ".join(paths[:30])
    return result[:500]


def _extract_whatweb_summary(result: str) -> str:
    """Trích xuất technology stack từ whatweb."""
    # WhatWeb output thường có format: URL [status] tech1, tech2, ...
    return result[:600]


def _extract_curl_summary(result: str) -> str:
    """Trích xuất thông tin quan trọng từ curl."""
    lines = result.split("\n")
    important = []
    for line in lines[:30]:
        line = line.strip()
        if not line:
            continue
        # Giữ status code, headers quan trọng, và vài dòng body
        if any(kw in line.lower() for kw in ["http/", "status", "content-type", "server:", "x-powered-by",
                                               "set-cookie", "location:", "access-control", "x-frame"]):
            important.append(line)
    # Thêm vài dòng body nếu có nội dung hữu ích
    body_preview = result[:300] if len(result) < 500 else ""
    summary = "\n".join(important[:15])
    if body_preview and not summary:
        summary = body_preview
    return summary or result[:400]


def save_recon(tool_name: str, tool_args: dict, tool_result: str) -> bool:
    """
    Lưu kết quả recon vào cache.
    
    Returns:
        True nếu lưu thành công (chưa có trong cache).
        False nếu đã tồn tại → SKIP.
    """
    cache = _load_cache()
    
    # === Xử lý các tool recon chính ===
    if tool_name in RECON_TOOLS:
        # Chuẩn hóa tên tool (vd: nmap_scan_ports → nmap_scan)
        cache_key = _TOOL_NAME_MAP.get(tool_name, tool_name)
        
        # ĐÃ CÓ RỒI → KHÔNG LƯU THÊM
        if cache_key in cache:
            return False
        
        # Trích xuất summary
        if cache_key == "nmap_scan":
            summary = _extract_nmap_summary(tool_result)
        elif cache_key == "dirb_web_scan":
            summary = _extract_dirb_summary(tool_result)
        elif cache_key == "whatweb_fingerprint":
            summary = _extract_whatweb_summary(tool_result)
        else:
            summary = tool_result[:500]
        
        cache[cache_key] = {
            "tool": tool_name,
            "args": tool_args,
            "summary": summary,
            "source": "auto",
        }
        _save_cache(cache)
        print(f"[RECON CACHE] Saved: {cache_key} ← {tool_name} ({len(summary)} chars)")
        return True
    
    # === Xử lý curl cho các URL quan trọng ===
    if tool_name == "curl_http_check":
        url = tool_args.get("url", "")
        # Kiểm tra xem URL có nằm trong danh sách quan trọng không
        path = re.sub(r"https?://[^/]+", "", url)
        is_important = any(imp in path for imp in IMPORTANT_URLS)
        
        if is_important:
            cache_key = f"curl:{path}"
            
            # ĐÃ CÓ RỒI → KHÔNG LƯU THÊM
            if cache_key in cache:
                return False
            
            method = tool_args.get("method", "GET")
            summary = _extract_curl_summary(tool_result)
            
            cache[cache_key] = {
                "tool": "curl_http_check",
                "method": method,
                "path": path,
                "summary": summary,
                "source": "auto",
            }
            _save_cache(cache)
            print(f"[RECON CACHE] Saved: {cache_key} ({len(summary)} chars)")
            return True
    
    return False


def get_recon_summary() -> Optional[str]:
    """
    Tạo chuỗi tóm tắt recon để inject vào prompt.
    
    Returns:
        Chuỗi tóm tắt nếu có dữ liệu cache, None nếu cache trống.
    """
    cache = _load_cache()
    if not cache:
        return None
    
    parts = []
    
    # 1. Thông tin từ các tool recon chính
    for tool_name in ["nmap_scan", "whatweb_fingerprint", "dirb_web_scan", "nikto_web_scan"]:
        if tool_name in cache:
            entry = cache[tool_name]
            label = {
                "nmap_scan": "NMAP (Port & Service Scan)",
                "whatweb_fingerprint": "WHATWEB (Technology Stack)",
                "dirb_web_scan": "DIRB (Directory Discovery)",
                "nikto_web_scan": "NIKTO (Web Vulnerability Scan)",
            }.get(tool_name, tool_name)
            parts.append(f"[{label}]\n{entry['summary']}")
    
    # 2. Thông tin từ curl các URL quan trọng
    curl_entries = [(k, v) for k, v in cache.items() if k.startswith("curl:")]
    if curl_entries:
        curl_lines = []
        for key, entry in sorted(curl_entries):
            path = entry.get("path", key)
            method = entry.get("method", "GET")
            summary_short = entry["summary"][:150].replace("\n", " ")
            curl_lines.append(f"  {method} {path} -> {summary_short}")
        parts.append("[CURL - Key Endpoints]\n" + "\n".join(curl_lines))
    
    if not parts:
        return None
    
    full_summary = "\n\n".join(parts)
    
    # Giới hạn độ dài
    if len(full_summary) > MAX_SUMMARY_LENGTH:
        full_summary = full_summary[:MAX_SUMMARY_LENGTH] + "\n... (đã cắt bớt)"
    
    return full_summary


def clear_cache() -> None:
    """Xóa toàn bộ cache (dùng khi đổi target hoặc reset)."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    print("[RECON CACHE] Cleared.")


def cache_status() -> dict:
    """Trả về trạng thái cache hiện tại."""
    cache = _load_cache()
    return {
        "total_entries": len(cache),
        "tools_cached": [k for k in cache if not k.startswith("curl:")],
        "curl_cached": [k for k in cache if k.startswith("curl:")],
        "cache_file": str(CACHE_FILE),
    }

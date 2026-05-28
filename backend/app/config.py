import json
import os
import threading
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from dotenv import load_dotenv

# Luôn đọc .env trong thư mục backend/, dù chạy uvicorn từ đâu
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"
load_dotenv(_ENV_FILE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    # Danh sách nhiều API keys, cách nhau bằng dấu phẩy
    gemini_api_keys: str = ""
    # Gemini Native client expects model name like: gemini-flash-latest
    openai_model: str = "gemini-2.5-flash"

    # Bật MCP: subprocess stdio (vd: Kali MCP hoặc demo_mcp_server.py)
    mcp_enabled: bool = True
    mcp_command: str = "python"
    # JSON array string, ví dụ: ["demo_mcp_server.py"]
    mcp_args_json: str = "[]"

    # Supabase (Postgres qua API) — chỉ dùng trên server, không commit key lên git
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    @property
    def mcp_args(self) -> list[str]:
        raw = self.mcp_args_json.strip()
        if not raw:
            return []
        return json.loads(raw)

    def default_demo_server_args(self) -> list[str]:
        demo = _BACKEND_ROOT / "demo_mcp_server.py"
        return [str(demo)]

    @property
    def backend_root(self) -> Path:
        return _BACKEND_ROOT


settings = Settings()


# ══════════════════════════════════════════════════════════════
# API Key Pool — Xoay tự động khi gặp rate limit
# ══════════════════════════════════════════════════════════════

class APIKeyPool:
    """
    Quản lý pool nhiều API keys cho Gemini.
    Tự động xoay sang key tiếp theo khi key hiện tại bị rate limit (429/503).
    
    Cách sử dụng:
    1. Đặt nhiều keys trong .env:  GEMINI_API_KEYS=key1,key2,key3
    2. Hoặc agent tự lấy từ openai_api_key nếu chỉ có 1 key
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._keys: list[str] = []
        self._index = 0
        self._error_counts: dict[int, int] = {}  # index → error count
        self._load_keys()
    
    def _load_keys(self):
        """Load API keys từ .env"""
        keys = []
        
        # 1. Đọc từ GEMINI_API_KEYS (ưu tiên)
        multi = settings.gemini_api_keys.strip()
        if multi:
            keys.extend([k.strip() for k in multi.split(",") if k.strip()])
        
        # 2. Đọc từ OPENAI_API_KEY (fallback)
        main_key = settings.openai_api_key.strip()
        if main_key and main_key not in keys:
            keys.insert(0, main_key)
        
        self._keys = keys
        self._error_counts = {i: 0 for i in range(len(keys))}
        
        if len(keys) > 1:
            print(f"[API_KEY_POOL] OK: Loaded {len(keys)} API keys. Auto-rotation enabled.")
        elif len(keys) == 1:
            print(f"[API_KEY_POOL] WARN: Chi co 1 API key. Them keys vao GEMINI_API_KEYS trong .env de tang quota.")
        else:
            print(f"[API_KEY_POOL] ERROR: Khong tim thay API key nao!")
    
    @property
    def current_key(self) -> str:
        """Lấy API key hiện tại."""
        if not self._keys:
            return settings.openai_api_key
        with self._lock:
            return self._keys[self._index]
    
    @property
    def key_count(self) -> int:
        return len(self._keys)
    
    @property
    def current_index(self) -> int:
        return self._index
    
    def rotate(self, reason: str = "") -> str:
        """
        Xoay sang API key tiếp theo.
        Trả về key mới.
        """
        if len(self._keys) <= 1:
            return self.current_key
        
        with self._lock:
            old_idx = self._index
            self._error_counts[old_idx] = self._error_counts.get(old_idx, 0) + 1
            
            # Tìm key có ít lỗi nhất (tránh key đã bị vắt kiệt)
            best_idx = (old_idx + 1) % len(self._keys)
            best_errors = self._error_counts.get(best_idx, 0)
            
            for i in range(len(self._keys)):
                if i == old_idx:
                    continue
                if self._error_counts.get(i, 0) < best_errors:
                    best_idx = i
                    best_errors = self._error_counts.get(i, 0)
            
            self._index = best_idx
            new_key = self._keys[self._index]
            masked = new_key[:10] + "..." + new_key[-4:]
            print(f"[API_KEY_POOL] ROTATE: key #{old_idx+1} -> #{self._index+1} ({masked}) | Reason: {reason}")
            return new_key
    
    def report_success(self):
        """Gọi khi request thành công — reset error count cho key hiện tại."""
        with self._lock:
            self._error_counts[self._index] = max(0, self._error_counts.get(self._index, 0) - 1)
    
    def status(self) -> dict:
        """Trả về trạng thái pool."""
        return {
            "total_keys": len(self._keys),
            "current_index": self._index + 1,
            "error_counts": {f"key_{i+1}": cnt for i, cnt in self._error_counts.items()},
            "keys_masked": [k[:10] + "..." + k[-4:] for k in self._keys],
        }


# Singleton
api_key_pool = APIKeyPool()

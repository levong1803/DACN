import json
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
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

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

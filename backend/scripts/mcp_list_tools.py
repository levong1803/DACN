"""Liệt kê tool từ MCP (demo server mặc định). Chạy: từ thư mục backend, PYTHONPATH=."""
import asyncio

from app.config import settings
from app.mcp_bridge import with_mcp_session


async def main() -> None:
    async def dump(_session, openai_tools):
        for t in openai_tools:
            print(t["function"]["name"], "-", t["function"]["description"][:60])

    await with_mcp_session(dump)


if __name__ == "__main__":
    asyncio.run(main())

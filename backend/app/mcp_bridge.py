import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.types import CallToolResult, TextContent

from .config import settings


def _mcp_subprocess_env() -> dict[str, str]:
    """
    MCP mặc định chỉ truyền vài biến (PATH, …). Merge thêm PENTEST_* và PYTHONPATH
    để process con thấy nmap/dirb và rule cho phép host.
    """
    base = get_default_environment()
    extra: dict[str, str] = {}
    wslenv_keys = []
    
    for key, value in os.environ.items():
        if key.startswith("PENTEST") or key in ("PYTHONPATH", "PYTHONHOME"):
            extra[key] = value
            wslenv_keys.append(f"{key}/u")
            
    if wslenv_keys:
        old_wslenv = os.environ.get("WSLENV", "")
        new_wslenv = ":".join(wslenv_keys)
        extra["WSLENV"] = f"{old_wslenv}:{new_wslenv}" if old_wslenv else new_wslenv
        
    return {**base, **extra}


def _mcp_args_resolved() -> list[str]:
    args = settings.mcp_args
    if not args:
        return settings.default_demo_server_args()
    return args


def mcp_tools_to_openai(mcp_tools: list[Any]) -> list[dict]:
    out: list[dict] = []
    for t in mcp_tools:
        schema = t.inputSchema if getattr(t, "inputSchema", None) else {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": (t.description or "").strip() or f"MCP tool: {t.name}",
                    "parameters": schema,
                },
            }
        )
    return out


def _tool_result_text(result: CallToolResult) -> str:
    parts: list[str] = []
    for block in result.content or []:
        if isinstance(block, TextContent):
            parts.append(block.text)
        else:
            parts.append(str(block))
    if result.isError:
        return "Lỗi tool: " + ("\n".join(parts) if parts else "unknown")
    return "\n".join(parts) if parts else "(empty)"


async def with_mcp_session[T](
    fn: Callable[[ClientSession, list[dict]], Awaitable[T]],
) -> T:
    """Mở một phiên MCP stdio, list tool OpenAI-format, gọi fn(session, openai_tools)."""
    params = StdioServerParameters(
        command=settings.mcp_command,
        args=_mcp_args_resolved(),
        env=_mcp_subprocess_env(),
        cwd=str(settings.backend_root),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            openai_tools = mcp_tools_to_openai(listed.tools)
            return await fn(session, openai_tools)


async def call_mcp_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> str:
    raw = await session.call_tool(name, arguments=arguments)
    return _tool_result_text(raw)


def parse_tool_arguments(arguments_json: str) -> dict[str, Any]:
    try:
        return json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError:
        return {}

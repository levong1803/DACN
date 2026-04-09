import uuid
from typing import Any

from openai import AsyncOpenAI

from .config import settings
from . import db
from .mcp_bridge import call_mcp_tool, parse_tool_arguments, with_mcp_session

SYSTEM = """Bạn là trợ lý thử nghiệm xâm nhập web tự động (chỉ mục tiêu được phép / lab).
Công cụ MCP có thể gồm: nmap_scan_ports, dirb_web_scan, hydra_http_login, echo, server_time.
Chỉ gọi nmap/dirb/hydra khi người dùng xác định rõ mục tiêu hợp pháp; dùng đúng tham số từ tool schema.
Không bịa kết quả khi có thể gọi tool. Giải thích ngắn sau mỗi bước."""


async def run_chat(
    user_message: str,
    session_id: str | None = None,
) -> tuple[str, str]:
    """
    Chạy một lượt chat: LLM + (tuỳ chọn) vòng lặp tool MCP.
    Trả về (assistant_text_cuối, session_id).
    """
    sid = session_id or str(uuid.uuid4())
    await db.log_entry(role="user", content=user_message, session_id=sid)

    if not settings.openai_api_key:
        msg = "Thiếu OPENAI_API_KEY trong .env (hoặc biến môi trường)."
        await db.log_entry(role="assistant", content=msg, session_id=sid)
        return msg, sid

    client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    if settings.mcp_enabled:
        return await _run_with_mcp(client, user_message, sid)

    return await _run_llm_only(client, user_message, sid)


async def _run_llm_only(client: AsyncOpenAI, user_message: str, sid: str) -> tuple[str, str]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_message},
    ]
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
    )
    text = resp.choices[0].message.content or ""
    await db.log_entry(role="assistant", content=text, session_id=sid)
    return text, sid


async def _run_with_mcp(client: AsyncOpenAI, user_message: str, sid: str) -> tuple[str, str]:
    async def body(session, openai_tools: list[dict]) -> tuple[str, str]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message},
        ]
        max_rounds = 20
        final_text = ""

        for _ in range(max_rounds):
            kwargs: dict[str, Any] = {
                "model": settings.openai_model,
                "messages": messages,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            resp = await client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls

            if tool_calls:
                assistant_payload: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                messages.append(assistant_payload)
                await db.log_entry(
                    role="assistant",
                    content=msg.content,
                    session_id=sid,
                    meta={"tool_calls": [tc.function.name for tc in tool_calls]},
                )

                for tc in tool_calls:
                    name = tc.function.name
                    args = parse_tool_arguments(tc.function.arguments or "")
                    result_text = await call_mcp_tool(session, name, args)
                    await db.log_entry(
                        role="tool",
                        session_id=sid,
                        tool_name=name,
                        tool_args=args,
                        tool_result=result_text[:8000],
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_text,
                        }
                    )
                continue

            final_text = msg.content or ""
            messages.append({"role": "assistant", "content": final_text})
            await db.log_entry(role="assistant", content=final_text, session_id=sid)
            break
        else:
            final_text = "Đã vượt giới hạn vòng lặp tool."
            await db.log_entry(role="assistant", content=final_text, session_id=sid)

        return final_text, sid

    return await with_mcp_session(body)

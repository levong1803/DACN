import asyncio
import uuid
import json
import httpx
from typing import Any

from .config import settings
from . import db
from .mcp_bridge import call_mcp_tool, parse_tool_arguments, with_mcp_session

# --- Native Gemini Client Helper ---
class GeminiNativeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": "" # Đảm bảo xóa bỏ mọi token thừa bị tiêm vào từ môi trường
        }

    async def embed_text(self, text: str) -> list[float]:
        url = f"{self.base_url}/models/gemini-embedding-001:embedContent?key={self.api_key}"
        payload = {"content": {"parts": [{"text": text}]}}
        # trust_env=False giúp bỏ qua các biến môi trường proxy/auth của máy tính
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]

    async def generate_content(self, model: str, messages: list[dict], tools: list[dict] = None) -> Any:
        # ... logic convert giữ nguyên ...
        contents = []
        for m in messages:
            if m.get("_raw_parts"):
                contents.append({"role": m.get("_role") or "model", "parts": m["_raw_parts"]})
                continue
            role = "user" if m["role"] == "user" else "model"
            if m["role"] == "system": role = "user" 
            parts = []
            if m.get("content"): parts.append({"text": m["content"]})
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    parts.append({"functionCall": {"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"])}})
            if m.get("role") == "tool":
                parts = [{"functionResponse": {"name": m.get("name") or "unknown", "response": {"result": m["content"]}}}]
                role = "user"
            contents.append({"role": role, "parts": parts})

        gemini_tools = []
        if tools:
            declarations = []
            for t in tools:
                f = t["function"]
                declarations.append({"name": f["name"], "description": f.get("description", ""), "parameters": f.get("parameters", {"type": "object", "properties": {}})})
            gemini_tools = [{"function_declarations": declarations}]

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        payload = {"contents": contents}
        if gemini_tools: payload["tools"] = gemini_tools

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            if resp.status_code != 200:
                error_data = resp.json()
                raise Exception(f"Gemini API Error: {error_data}")
            
            data = resp.json()
            candidate = data["candidates"][0]
            gemini_msg = candidate["content"]
            text_content = ""
            tool_calls = []
            for part in gemini_msg.get("parts", []):
                if "text" in part: text_content += part["text"]
                if "functionCall" in part:
                    fn = part["functionCall"]
                    tool_calls.append(type('obj', (object,), {
                        'id': f"call_{uuid.uuid4().hex[:12]}",
                        'function': type('obj', (object,), {'name': fn["name"], 'arguments': json.dumps(fn.get("args", {}))})
                    }))
            return type('obj', (object,), {'choices': [type('obj', (object,), {'message': type('obj', (object,), {'content': text_content, 'tool_calls': tool_calls if tool_calls else None, '_raw_parts': gemini_msg.get("parts"), '_role': gemini_msg.get("role")})})]})
            
            return type('obj', (object,), {
                'choices': [type('obj', (object,), {
                    'message': type('obj', (object,), {
                        'content': text_content,
                        'tool_calls': tool_calls if tool_calls else None,
                        '_raw_parts': gemini_msg.get("parts"),
                        '_role': gemini_msg.get("role")
                    })
                })]
            })

SYSTEM = """Bạn là chuyên gia thử nghiệm xâm nhập web (penetration tester) tự động, tuân theo chuẩn OWASP WSTG.
Chỉ kiểm thử trên mục tiêu được phép hoặc môi trường lab.

Các tool MCP có sẵn (gọi đúng tên):
- nmap_scan_ports(target, ports)         — Quét cổng, phát hiện service
- dirb_web_scan(url, wordlist)           — Dò thư mục/file ẩn
- hydra_http_login(host, port, user, pass, path) — Brute-force login
- sqlmap_web_scan(url, level, risk)      — Phát hiện SQL Injection
- nikto_web_scan(url, tuning)            — Quét lỗ hổng web server
- whatweb_fingerprint(target, aggression) — Nhận diện công nghệ web
- wafw00f_waf_detect(target)             — Phát hiện WAF
- dnsrecon_lookup(domain, scan_type)     — Thu thập thông tin DNS
- testssl_check(target)                  — Kiểm tra SSL/TLS
- curl_http_check(url, method)           — Kiểm tra HTTP headers
- commix_cmd_inject(url)                 — Kiểm tra Command Injection
- wfuzz_web_fuzz(url, wordlist, hide_code) — Fuzzing web
- tplmap_ssti_scan(url)                  — Kiểm tra SSTI
- zap_web_scan(target, scan_type)        — Quét toàn diện với ZAP
- reconng_osint(domain, module)          — Thu thập OSINT
- padbuster_oracle(url, encrypted, block_size) — Padding Oracle
- echo(text)                             — Kiểm tra kết nối MCP
- server_time()                          — Thời gian server

Nguyên tắc: Gọi tool phù hợp nhất với yêu cầu WSTG. Không bịa kết quả. Giải thích ngắn sau mỗi bước công cụ."""


async def run_chat(
    user_message: str,
    session_id: str | None = None,
) -> tuple[str, str]:
    sid = session_id or str(uuid.uuid4())
    await db.log_entry(role="user", content=user_message, session_id=sid)

    if not settings.openai_api_key:
        msg = "Thiếu API KEY trong .env."
        await db.log_entry(role="assistant", content=msg, session_id=sid)
        return msg, sid

    client = GeminiNativeClient(api_key=settings.openai_api_key)

    system_prompt = SYSTEM
    try:
        query_embedding = await client.embed_text(user_message)
        kb_results = await db.search_wstg_kb(query_embedding, match_threshold=0.3, match_count=2)
        if kb_results:
            rag_info = "\n\n".join([r['content'] for r in kb_results])
            system_prompt += (
                f"\n\n[HỆ THỐNG RAG - KẾT QUẢ TÌM KIẾM WSTG]\n"
                f"Bối cảnh liên quan:\n{rag_info}\n"
                f"Hãy dùng thông tin trên để hỗ trợ pentest."
            )
    except Exception as e:
        print(f"RAG Retrieval Error: {e}")

    if settings.mcp_enabled:
        return await _run_with_mcp(client, user_message, sid, system_prompt)

    return await _run_llm_only(client, user_message, sid, system_prompt)


async def _run_llm_only(client: GeminiNativeClient, user_message: str, sid: str, system_prompt: str) -> tuple[str, str]:
    messages = [
        {"role": "user", "content": system_prompt + "\n\nUser request: " + user_message},
    ]
    resp = await client.generate_content(model=settings.openai_model, messages=messages)
    text = resp.choices[0].message.content or ""
    await db.log_entry(role="assistant", content=text, session_id=sid)
    return text, sid


async def _run_with_mcp(client: GeminiNativeClient, user_message: str, sid: str, system_prompt: str) -> tuple[str, str]:
    async def body(session, openai_tools: list[dict]) -> tuple[str, str]:
        messages = [
            {"role": "user", "content": system_prompt + "\n\nYêu cầu người dùng: " + user_message},
        ]
        max_rounds = 10
        final_text = ""

        for _ in range(max_rounds):
            resp = await client.generate_content(
                model=settings.openai_model,
                messages=messages,
                tools=openai_tools
            )
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls

            if tool_calls:
                assistant_payload = {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                    "_raw_parts": getattr(msg, "_raw_parts", None),
                    "_role": getattr(msg, "_role", None)
                }
                messages.append(assistant_payload)

                for tc in tool_calls:
                    name = tc.function.name
                    args = parse_tool_arguments(tc.function.arguments or "")
                    result_text = await call_mcp_tool(session, name, args)
                    await db.log_entry(
                        role="tool", session_id=sid, tool_name=name,
                        tool_args=args, tool_result=result_text[:8000],
                    )
                    messages.append({
                        "role": "tool",
                        "name": name,
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })
                continue

            final_text = msg.content or ""
            await db.log_entry(role="assistant", content=final_text, session_id=sid)
            break
        else:
            final_text = "Đã vượt giới hạn vòng lặp tool."
            await db.log_entry(role="assistant", content=final_text, session_id=sid)
        
        return final_text, sid

    return await with_mcp_session(body)

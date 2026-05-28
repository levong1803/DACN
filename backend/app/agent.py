import asyncio
import uuid
import json
import httpx
from typing import Any

from .config import settings, api_key_pool
from . import db
from .mcp_bridge import call_mcp_tool, parse_tool_arguments, with_mcp_session
from .prompt_logger import log_prompt, log_tool_call, log_llm_response
from .recon_cache import save_recon, get_recon_summary

class GeminiNativeClient:
    def __init__(self, api_key: str | None = None):
        # Sử dụng key từ pool nếu không truyền vào
        self.api_key = (api_key or api_key_pool.current_key).strip()
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.headers = {"Content-Type": "application/json"}

    def _get_current_key(self) -> str:
        """Lấy key hiện tại từ pool (luôn lấy mới nhất)."""
        return api_key_pool.current_key

    async def embed_text(self, text: str) -> list[float]:
        key = self._get_current_key()
        url = f"{self.base_url}/models/gemini-embedding-001:embedContent?key={key}"
        payload = {"content": {"parts": [{"text": text}]}}
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            for attempt in range(api_key_pool.key_count + 2):
                resp = await client.post(url, headers=self.headers, json=payload)
                if resp.status_code in (403, 429, 503):
                    new_key = api_key_pool.rotate(reason=f"embed {resp.status_code}")
                    url = f"{self.base_url}/models/gemini-embedding-001:embedContent?key={new_key}"
                    await asyncio.sleep(2)
                    continue
                resp.raise_for_status()
                api_key_pool.report_success()
                return resp.json()["embedding"]["values"]
            raise Exception("Embed: tất cả API keys đều bị rate limit")

    async def generate_content(self, model: str, messages: list[dict], tools: list[dict] = None) -> Any:
        contents = []
        for m in messages:
            if m.get("_raw_parts"):
                contents.append({"role": m.get("_role") or "model", "parts": m["_raw_parts"]})
                continue
            role = "user" if m["role"] in ["user", "system"] else "model"
            parts = []
            if m.get("content"): parts.append({"text": m["content"]})
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    parts.append({"functionCall": {"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"])}})
            if m.get("role") == "tool":
                parts = [{"functionResponse": {"name": m.get("name") or "unknown", "response": {"result": m["content"]}}}]
                role = "user"
            contents.append({"role": role, "parts": parts})

        gemini_tools = [{"function_declarations": [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "parameters": t["function"].get("parameters", {"type": "object", "properties": {}})} for t in tools]}] if tools and len(tools) > 0 else []

        body = {"contents": contents, "tools": gemini_tools} if gemini_tools else {"contents": contents}

        # Retry logic with KEY ROTATION on 429/503
        max_attempts = max(5, api_key_pool.key_count * 2)  # Nhiều key = nhiều lần thử hơn
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            for attempt in range(max_attempts):
                current_key = self._get_current_key()
                url = f"{self.base_url}/models/{model}:generateContent?key={current_key}"
                resp = await client.post(url, headers=self.headers, json=body)
                if resp.status_code in (403, 429, 503):
                    # Xoay sang key khác NGAY LẬP TỨC thay vì chờ lâu
                    reason = f"generate {resp.status_code} (attempt {attempt+1}/{max_attempts})"
                    api_key_pool.rotate(reason=reason)
                    wait = 3 if api_key_pool.key_count > 1 else 5 * (attempt + 1)
                    print(f"[RETRY] {resp.status_code} attempt {attempt+1}, rotating key, wait {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    raise Exception(f"Gemini API Error: {resp.json()}")
                api_key_pool.report_success()
                return self._parse_gemini_resp(resp.json())
            raise Exception(f"Gemini API: vượt quá retry limit ({resp.status_code}). Tất cả {api_key_pool.key_count} keys đều hết quota.")

    def _parse_gemini_resp(self, data: dict) -> Any:
        candidates = data.get("candidates", [])
        if not candidates:
            raise Exception(f"Gemini trả về rỗng (có thể bị safety block): {data}")
        msg = candidates[0].get("content", {})
        raw_parts = msg.get("parts", [])

        # Lọc bỏ thought parts (thinking models) — chỉ giữ text và functionCall
        clean_parts = [p for p in raw_parts if "thought" not in p]

        text_content = "".join([p["text"] for p in clean_parts if "text" in p])
        tool_calls = []
        for part in clean_parts:
            if "functionCall" in part:
                fn = part["functionCall"]
                tool_calls.append(type('obj', (object,), {
                    'id': f"call_{uuid.uuid4().hex[:12]}",
                    'function': type('obj', (object,), {'name': fn["name"], 'arguments': json.dumps(fn.get("args", {}))})
                }))
        return type('obj', (object,), {'choices': [type('obj', (object,), {'message': type('obj', (object,), {'content': text_content, 'tool_calls': tool_calls if tool_calls else None, '_raw_parts': clean_parts, '_role': msg.get("role")})})]})


SYSTEM = """Bạn là chuyên gia Pentester tuân thủ OWASP WSTG.

[QUY TẮC]:
1. ƯU TIÊN RAG: Nếu có phần [HỆ THỐNG RAG] bên dưới, PHẢI thực hiện theo quy trình và tools được gợi ý trong đó trước.
2. CHIẾN LƯỢC: Bắt đầu bằng reconnaissance (nmap, whatweb, curl) → sau đó dùng tools chuyên sâu (sqlmap, nikto, hydra...) dựa trên kết quả bước trước.
3. CHAIN OF EVIDENCE: Dùng kết quả tool trước làm đầu vào cho tool sau. Không lặp lại tool đã chạy với cùng tham số.
4. KHÔNG LƯỜI: Nếu tool báo không tìm thấy lỗi, thử endpoint/payload khác trước khi kết luận PASS.
5. KẾT LUẬN: Chỉ PASS khi có ít nhất 2 bằng chứng sạch. Ưu tiên ISSUE hoặc NEEDS_REVIEW nếu nghi ngờ.
6. ĐÀO SÂU: Khi dirb/wfuzz tìm thấy path mới → PHẢI dùng curl_http_check(GET) kiểm tra NỘI DUNG từng path quan trọng (ví dụ: /ftp/, /admin/, /api/, /metrics, /robots.txt). Không được bỏ qua path đã tìm thấy.
7. SPA AWARENESS: Ứng dụng Angular/React là SPA — mọi route trả cùng 1 HTML. Tập trung kiểm tra các API endpoint (/api/*, /rest/*) thay vì route frontend. Kiểm tra /robots.txt để tìm path ẩn.
8. VERIFY FINDINGS: Với mỗi phát hiện, phải có 1 bước verify cụ thể (curl GET để xem nội dung, hoặc thử truy cập endpoint đó).
9. MUST-TEST ENDPOINTS: Dù dirb có tìm thấy hay không, LUÔN dùng curl kiểm tra các endpoint phổ biến sau: /robots.txt, /rest/user/login, /rest/products/search?q=test, /api/Users/, /api/Feedbacks, /api/Products/, /ftp/, /administration. Đây là các API endpoint mà dirb không phát hiện được trong SPA.
10. AUTHENTICATED TESTING: Nếu cần kiểm tra endpoint yêu cầu đăng nhập, dùng tool curl_authenticated_check để tự động login và gửi request có JWT token.
11. JWT ANALYSIS: Khi nhận được chuỗi JWT token từ phản hồi đăng nhập hoặc API, LUÔN dùng công cụ jwt_decode_tool để tự động giải mã Base64Url sang cấu trúc JSON rõ ràng và kiểm tra tĩnh các claims nhạy cảm trong Header/Payload thay vì kết luận không thể phân tích.

[BÁO CÁO]: Kết thúc bằng:
[CONCLUSION]: PASS hoặc ISSUE hoặc NEEDS_REVIEW
[SUMMARY]: Tóm tắt kỹ thuật chi tiết"""


# Endpoint hints cho từng nhóm WSTG 
ENDPOINT_HINTS = {
    "INPV": """[GỢI Ý ENDPOINT - Input Validation]:
- SQL Injection: /rest/products/search?q=' OR 1=1--, /rest/user/login (email field)
- XSS: /rest/products/search?q=<script>alert(1)</script>, /api/Feedbacks (comment field), /#/search?q=<payload>
- Command Injection: Tìm endpoint có tham số xử lý file/path
- SSRF: /profile/image/url, /api endpoint có tham số URL""",
    "ATHN": """[GỢI Ý ENDPOINT - Authentication]:
- Login: /rest/user/login (POST, body: {"email":"...","password":"..."})
- Default creds: admin@juice-sh.op / admin123
- Password reset: /rest/user/reset-password
- Registration: /api/Users/ (POST)""",
    "ATHZ": """[GỢI Ý ENDPOINT - Authorization]:
- IDOR: /api/Users/1, /api/Users/2 (đổi ID để xem user khác)
- Basket: /api/BasketItems/1, /rest/basket/1 (xem giỏ hàng người khác)
- Admin: /administration, /api/Users/ (liệt kê tất cả users)
- Path traversal: /ftp/../../etc/passwd""",
    "SESS": """[GỢI Ý ENDPOINT - Session]:
- Login để lấy token: /rest/user/login → response chứa JWT
- Cookie flags: Kiểm tra Set-Cookie headers (Secure, HttpOnly, SameSite)
- CSRF: /api/Feedbacks (POST không cần CSRF token)
- JWT decode: Dùng công cụ jwt_decode_tool để tự động giải mã JWT Base64Url, phân tích tĩnh Header và Payload để tìm thông tin cá nhân hoặc phân quyền nhạy cảm bị lộ""",
    "CONF": """[GỢI Ý ENDPOINT - Configuration]:
- Admin interface: /administration, /ftp/ (directory listing)
- Sensitive files: /robots.txt, /.env, /.git/
- Security headers: Kiểm tra CSP, HSTS, X-Frame-Options từ response headers
- CORS: Kiểm tra Access-Control-Allow-Origin header""",
    "CLNT": """[GỢI Ý ENDPOINT - Client-Side]:
- DOM XSS: /#/search?q=<payload> (hash fragment được Angular xử lý)
- Redirect: /redirect?to=<url>
- Clickjacking: Kiểm tra X-Frame-Options header
- LocalStorage: Ứng dụng có thể lưu token trong localStorage""",
    "BUSL": """[GỢI Ý ENDPOINT - Business Logic]:
- Price manipulation: /api/BasketItems/ (sửa price/quantity)
- Negative quantity: /api/Quantitys/ (đặt số lượng âm)
- Coupon abuse: /rest/basket/X/coupon/COUPON_CODE""",
    "ERRH": """[GỢI Ý ENDPOINT - Error Handling]:
- Verbose errors: /api/nonexistent, /rest/products/search?q=' (SQL error)
- Stack traces: Gửi request sai format tới /api/Users/""",
}

async def run_chat(user_message: str, session_id: str | None = None, wstg_id: str | None = None) -> tuple[str, str]:
    sid = session_id or str(uuid.uuid4())
    await db.log_entry(role="user", content=user_message, session_id=sid, wstg_id=wstg_id)
    if not api_key_pool.current_key: return "Thiếu API KEY.", sid

    client = GeminiNativeClient()  # Tự động lấy key từ pool
    system_prompt = SYSTEM
    
    # === Tracking prompt components cho logging ===
    _rag_context = None
    _endpoint_hints = None
    _chain_evidence = None
    
    try:
        query_emb = await client.embed_text(user_message)
        context_items = await db.search_wstg_kb(query_emb)
        if context_items:
            import re as _re
            rag_parts = []
            for item in context_items:
                content = item.get('content', '')
                # Trích xuất WSTG ID từ nội dung (dòng đầu tiên: "ID: WSTG-XXXX-XX")
                id_match = _re.search(r'(?:ID:\s*)(WSTG-[A-Z]+-\d+|OTG-[A-Z]+-\d+)', content)
                label = id_match.group(1) if id_match else f"KB#{item.get('id', '?')}"
                sim = item.get('similarity', '')
                sim_str = f" (similarity: {sim:.2f})" if isinstance(sim, (int, float)) else ""
                rag_parts.append(f"--- {label}{sim_str} ---\n{content}")
            _rag_context = "\n\n".join(rag_parts)
            system_prompt += "\n\n[HỆ THỐNG RAG]\n" + _rag_context
    except Exception as e:
        print(f"RAG Error (non-fatal, AI sẽ chạy không có RAG): {e}")

    # Inject endpoint hints dựa trên nhóm WSTG (INPV, ATHN, CONF, SESS, ...)
    if wstg_id:
        category = wstg_id.split("-")[1] if "-" in wstg_id else ""
        if category in ENDPOINT_HINTS:
            _endpoint_hints = ENDPOINT_HINTS[category]
            system_prompt += "\n\n" + _endpoint_hints

    # === SHARED RECON CACHE: Inject dữ liệu trinh sát từ các test trước ===
    _recon_summary = None
    try:
        _recon_summary = get_recon_summary()
        if _recon_summary:
            system_prompt += "\n\n[DỮ LIỆU TRINH SÁT TỪ CÁC TEST TRƯỚC - KHÔNG CẦN CHẠY LẠI CÁC TOOL NÀY]\n" + _recon_summary
            system_prompt += "\n\n[LƯU Ý]: Dữ liệu trinh sát ở trên đã được thu thập từ các test trước. Hãy SỬ DỤNG trực tiếp thay vì chạy lại nmap/dirb/whatweb. Tập trung vào các tool chuyên sâu cho mục tiêu test hiện tại."
            print(f"[RECON CACHE] Injected {len(_recon_summary)} chars of prior recon data")
    except Exception as e:
        print(f"[RECON CACHE] Error loading cache (non-fatal): {e}")

    if wstg_id:
        # Lấy TẤT CẢ evidence từ mọi session cho wstg_id này (không giới hạn session hiện tại)
        history = await db.list_wstg_logs(wstg_id)
        findings = [f"Tool {h['tool_name']} kết quả: {(h.get('tool_result') or '')[:500]}" for h in history if h.get('role') == 'tool' and h.get('tool_name')]
        # Giới hạn tối đa 10 evidence gần nhất để tránh prompt quá dài
        if findings:
            recent = findings[-10:] if len(findings) > 10 else findings
            _chain_evidence = "\n".join(recent)
            system_prompt += f"\n\n[CHAIN OF EVIDENCE - {len(recent)} bằng chứng]\n" + _chain_evidence

    # === LOG PROMPT GỬI LÊN LLM ===
    log_prompt(
        wstg_id=wstg_id,
        session_id=sid,
        system_prompt=system_prompt,
        user_message=user_message,
        rag_context=_rag_context,
        endpoint_hints=_endpoint_hints,
        chain_of_evidence=_chain_evidence,
        recon_cache_data=_recon_summary,
        round_num=0,
        direction="TO_LLM",
    )

    if settings.mcp_enabled: return await _run_with_mcp(client, user_message, sid, system_prompt, wstg_id)
    return await _run_llm_only(client, user_message, sid, system_prompt, wstg_id)

async def _run_llm_only(client: GeminiNativeClient, user_message: str, sid: str, system_prompt: str, wstg_id: str | None = None) -> tuple[str, str]:
    messages = [
        {"role": "user", "content": system_prompt},
        {"role": "model", "content": "Đã hiểu. Tôi sẽ tuân thủ quy trình RAG và báo cáo theo đúng format."},
        {"role": "user", "content": user_message},
    ]
    resp = await client.generate_content(model=settings.openai_model, messages=messages)
    text = resp.choices[0].message.content or ""
    await db.log_entry(role="assistant", content=text, session_id=sid, wstg_id=wstg_id)
    return text, sid

async def _run_with_mcp(client: GeminiNativeClient, user_message: str, sid: str, system_prompt: str, wstg_id: str | None = None) -> tuple[str, str]:
    async def body(session, openai_tools: list[dict]) -> tuple[str, str]:
        tool_names = [t["function"]["name"] for t in openai_tools]
        messages = [
            {"role": "user", "content": system_prompt},
            {"role": "model", "content": "Đã hiểu. Tôi sẽ tuân thủ quy trình RAG, sử dụng tools theo chiến lược, và báo cáo theo format."},
            {"role": "user", "content": user_message},
        ]
        final_text = ""
        tools_used = []  # Theo dõi các tool đã chạy để tạo báo cáo fallback
        
        try:
            for round_num in range(30):
                resp = await client.generate_content(model=settings.openai_model, messages=messages, tools=openai_tools)
                msg = resp.choices[0].message
                if msg.tool_calls:
                    tc_names = [tc.function.name for tc in msg.tool_calls]
                    log_llm_response(
                        wstg_id=wstg_id, session_id=sid, round_num=round_num,
                        has_tool_calls=True, tool_call_names=tc_names,
                        text_content_preview=msg.content,
                    )
                    messages.append({"role": "assistant", "content": msg.content, "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls], "_raw_parts": getattr(msg, "_raw_parts", None), "_role": getattr(msg, "_role", None)})
                    for tc in msg.tool_calls:
                        name, args = tc.function.name, parse_tool_arguments(tc.function.arguments or "")
                        res = await call_mcp_tool(session, name, args)
                        # Loại bỏ null bytes — PostgreSQL không chấp nhận \u0000 trong text
                        res = res.replace('\x00', '')
                        tools_used.append(f"{name}({', '.join(f'{k}={v}' for k,v in args.items())})")
                        
                        await db.log_entry(role="tool", session_id=sid, tool_name=name, tool_args=args, tool_result=res[:30000], wstg_id=wstg_id)
                        # === RECON CACHE: Lưu kết quả recon (chỉ lưu 1 lần, có rồi thì skip) ===
                        try:
                            saved = save_recon(tool_name=name, tool_args=args, tool_result=res)
                            if saved:
                                print(f"[RECON CACHE] New recon saved from {wstg_id}: {name}")
                        except Exception as _cache_err:
                            print(f"[RECON CACHE] Save error (non-fatal): {_cache_err}")
                        # Log tool call
                        log_tool_call(
                            wstg_id=wstg_id, session_id=sid, round_num=round_num,
                            tool_name=name, tool_args=args, tool_result_preview=res[:500],
                        )
                        # Smart truncation: giữ đầu + cuối để AI thấy cả summary và vulnerabilities
                        if len(res) > 15000:
                            ai_res = res[:6000] + f"\n\n... [BỊ CẮT {len(res)-12000} ký tự] ...\n\n" + res[-6000:]
                        else:
                            ai_res = res
                        messages.append({"role": "tool", "name": name, "tool_call_id": tc.id, "content": ai_res})

                    continue
                final_text = msg.content or ""
                # Log final response
                import re as _re_final
                _conclusion = None
                _cm = _re_final.search(r"\[CONCLUSION\]:\s*\[?(PASS|ISSUE|NEEDS_REVIEW)\]?", final_text, _re_final.IGNORECASE)
                if _cm: _conclusion = _cm.group(1)
                log_llm_response(
                    wstg_id=wstg_id, session_id=sid, round_num=round_num,
                    has_tool_calls=False, text_content_preview=final_text[:300],
                    conclusion=_conclusion,
                )
                break
            else:
                final_text = final_text or "Đã đạt giới hạn vòng lặp tool (30 rounds). Kết quả có thể chưa đầy đủ."
        except Exception as e:
            # Nếu lỗi giữa chừng (429 hết retry, timeout, ...) → tạo báo cáo từ evidence đã có
            error_msg = f"{type(e).__name__}: {e}"
            print(f"[TOOL LOOP ERROR] Round {round_num if 'round_num' in dir() else '?'}: {error_msg}")
            final_text = f"⚠️ Quá trình kiểm thử bị gián đoạn do lỗi: {error_msg}\n\n"
            if tools_used:
                final_text += f"Các tool đã chạy trước khi lỗi:\n" + "\n".join(f"  - {t}" for t in tools_used)
            final_text += "\n\n[CONCLUSION]: NEEDS_REVIEW\n[SUMMARY]: Kiểm thử bị gián đoạn giữa chừng. Cần chạy lại để có kết quả đầy đủ."

        # Xử lý text rỗng (safety block hoặc AI không trả kết luận)
        if not final_text.strip():
            final_text = "⚠️ AI không trả về kết luận (có thể bị safety block hoặc hết token).\n\n"
            if tools_used:
                final_text += f"Các tool đã chạy thành công:\n" + "\n".join(f"  - {t}" for t in tools_used)
            final_text += "\n\n[CONCLUSION]: NEEDS_REVIEW\n[SUMMARY]: AI không đưa ra kết luận. Cần kiểm tra lại log tool để đánh giá thủ công."

        await db.log_entry(role="assistant", content=final_text, session_id=sid, wstg_id=wstg_id)
        return final_text, sid
    return await with_mcp_session(body)


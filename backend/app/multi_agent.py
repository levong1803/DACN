import asyncio
from typing import List, Dict, Any
import re
from urllib.parse import urlparse

from app.knowledge_graph import DynamicKnowledgeGraph
from app.rag_enhancer import RAGEnhancer


def _extract_target_url(text: str) -> str:
    """Trích xuất URL mục tiêu từ message của user bằng regex.
    Ưu tiên pattern 'Target: <url>', nếu không có thì tìm http://... đầu tiên."""
    # Pattern 1: Target: http://...
    m = re.search(r'Target:\s*(https?://\S+)', text, re.IGNORECASE)
    if m:
        return m.group(1).rstrip('.')
    # Pattern 2: URL bất kỳ
    m = re.search(r'(https?://\S+)', text)
    if m:
        return m.group(1).rstrip('.')
    return ""

class Verifier:
    """Xác thực kết quả phát hiện lỗ hổng."""
    
    SYSTEM_PROMPT = """Bạn là Verifier - chuyên gia xác thực kết quả phân tích bảo mật.
Bạn sẽ nhận được mô tả về lỗ hổng được phát hiện và output/bằng chứng từ công cụ.

Hãy phân tích cẩn thận bằng chứng (ví dụ: HTTP response code, nội dung response trả về, 
payload SQLi có thực thi thành công không) và đưa ra quyết định xác thực.

TRẢ VỀ ĐÚNG FORMAT JSON SAU:
{
    "verdict": "TRUE_POSITIVE" | "FALSE_POSITIVE" | "INCONCLUSIVE",
    "confidence": <int từ 0 đến 100>,
    "reason": "<lời giải thích ngắn gọn tại sao>"
}
"""

    def __init__(self, client):
        self.client = client
        from app.config import settings
        self.model = settings.openai_model

    async def verify(self, finding: str, evidence: str) -> Dict[str, Any]:
        prompt = f"Phát hiện: {finding}\n\nBằng chứng/Output từ tool:\n{evidence[:5000]}"
        messages = [
            {"role": "user", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        try:
            print(f"[MULTI-AGENT] 🔍 Verifier đang xác thực phát hiện...")
            resp = await self.client.generate_content(model=self.model, messages=messages)
            text = resp.choices[0].message.content or "{}"
            
            import json
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                verdict = json.loads(match.group(0))
                print(f"[MULTI-AGENT] 🔍 Verifier verdict: {verdict.get('verdict')} (confidence: {verdict.get('confidence')}%)")
                return verdict
            print(f"[MULTI-AGENT] ⚠️ Verifier không parse được JSON từ response")
            return {"verdict": "INCONCLUSIVE", "confidence": 0, "reason": "Failed to parse Verifier response."}
        except Exception as e:
            print(f"[MULTI-AGENT] ❌ Verifier error: {e}")
            return {"verdict": "INCONCLUSIVE", "confidence": 0, "reason": f"Error: {e}"}

class ReconAgent:
    """Đặc vụ Trinh Sát - CHỈ gọi các tool thu thập thông tin."""
    
    ALLOWED_TOOLS = {
        "nmap_scan", "nmap_scan_ports", "dirb_web_scan", "curl_http_check", "whatweb_fingerprint", "nikto_web_scan",
        "dnsrecon_lookup", "wafw00f_waf_detect",
        "graphql_introspection_check"
    }

    SYSTEM_PROMPT = """Bạn là Recon Agent - đặc vụ thu thập thông tin.
NHIỆM VỤ CỦA BẠN:
1. Bạn sẽ nhận được một lệnh/task từ Planner.
2. Bạn CHỈ được phép dùng các CÔNG CỤ (TOOLS) sau để tìm kiếm thông tin:
- nmap_scan, nmap_scan_ports
- dirb_web_scan: Dò thư mục web. Để tìm API ẩn trên các trang SPA/JS, HÃY truyền thêm wordlist (ví dụ: '/usr/share/dirb/wordlists/big.txt' hoặc tương tự).
- curl_http_check
- whatweb_fingerprint
- nikto_web_scan
- dnsrecon_lookup
- wafw00f_waf_detect
- graphql_introspection_check.
3. KHÔNG ĐƯỢC gọi các tool tấn công (sqlmap, commix, hydra, wfuzz, zap).
4. Chạy tool, sau đó báo cáo kết quả tóm tắt lại cho Planner. Đừng kết luận về lỗ hổng, chỉ mô tả dữ liệu bạn thu được.
5. Sau khi chạy xong tool và có kết quả, hãy TÓM TẮT ngắn gọn rồi KẾT THÚC. Không chạy thêm tool nếu đã hoàn thành task.
"""

    def __init__(self, client, session_id: str, dkg: DynamicKnowledgeGraph, target_url: str = ""):
        self.client = client
        self.session_id = session_id
        self.dkg = dkg
        self.target_url = target_url
        
    async def execute(self, task: str, wstg_id: str | None = None) -> str:
        from app.agent import _run_with_mcp
        custom_system = self.SYSTEM_PROMPT
        url_hint = f"\n\n[MỤC TIÊU ĐÃ XÁC ĐỊNH]: {self.target_url}" if self.target_url else ""
        print(f"[MULTI-AGENT] 🔍 ReconAgent bắt đầu thực thi task (target={self.target_url})...")
        result, _ = await _run_with_mcp(
            self.client, f"Nhiệm vụ của bạn:\n{task}{url_hint}\n\nHãy thực hiện NGAY LẬP TỨC bằng các tool trinh sát. URL mục tiêu đã cho ở trên, KHÔNG ĐƯỢC hỏi lại. Chạy tool và tóm tắt kết quả.", 
            self.session_id, custom_system, wstg_id=wstg_id,
            allowed_tools=self.ALLOWED_TOOLS
        )
        print(f"[MULTI-AGENT] 🔍 ReconAgent hoàn thành ({len(result)} chars)")
        return result

class ExploitAgent:
    """Đặc vụ Khai Thác - CHỈ gọi các tool tấn công + curl để verify."""
    
    ALLOWED_TOOLS = {
        "sqlmap_web_scan", "commix_cmd_inject",
        "hydra_brute_force", "wfuzz_web_fuzz",
        "zap_ajax_spider", "zap_active_scan", "zap_web_scan",
        "curl_http_check",  # Cần để xác minh kết quả khai thác
    }

    SYSTEM_PROMPT = """Bạn là Exploit Agent - đặc vụ khai thác lỗ hổng.
NHIỆM VỤ CỦA BẠN:
1. Bạn sẽ nhận được một lệnh/task tấn công từ Planner.
2. Bạn được quyền sử dụng các tool tấn công: sqlmap_web_scan, commix_cmd_inject, hydra_brute_force, wfuzz_web_fuzz, zap_web_scan, zap_active_scan, zap_ajax_spider.
3. Bạn cũng có curl_http_check để xác minh kết quả khai thác.
4. Chạy tool, sau đó báo cáo chi tiết kết quả khai thác: Payload nào đã thành công? Hay thất bại? Lỗi là gì?
5. Sau khi chạy xong tool và có kết quả, hãy TÓM TẮT ngắn gọn rồi KẾT THÚC. Không chạy thêm tool nếu đã hoàn thành task.
"""

    def __init__(self, client, session_id: str, dkg: DynamicKnowledgeGraph, target_url: str = ""):
        self.client = client
        self.session_id = session_id
        self.dkg = dkg
        self.target_url = target_url
        
    async def execute(self, task: str, wstg_id: str | None = None) -> str:
        from app.agent import _run_with_mcp
        custom_system = self.SYSTEM_PROMPT
        url_hint = f"\n\n[MỤC TIÊU ĐÃ XÁC ĐỊNH]: {self.target_url}" if self.target_url else ""
        print(f"[MULTI-AGENT] ⚔️ ExploitAgent bắt đầu thực thi task (target={self.target_url})...")
        result, _ = await _run_with_mcp(
            self.client, f"Nhiệm vụ của bạn:\n{task}{url_hint}\n\nHãy thực hiện NGAY LẬP TỨC bằng các tool khai thác. URL mục tiêu đã cho ở trên, KHÔNG ĐƯỢC hỏi lại. Chạy tool và báo cáo kết quả.", 
            self.session_id, custom_system, wstg_id=wstg_id,
            allowed_tools=self.ALLOWED_TOOLS  # ENFORCE: chỉ truyền tool tấn công + curl
        )
        print(f"[MULTI-AGENT] ⚔️ ExploitAgent hoàn thành ({len(result)} chars)")
        return result

class PlannerAgent:
    """Chỉ huy - Đọc DKG, lên kế hoạch, phân chia việc cho Recon/Exploit, tổng hợp kết quả."""

    SYSTEM_PROMPT = """Bạn là Planner Agent - chuyên gia lập kế hoạch pentest (Chỉ huy).
NHIỆM VỤ:
1. Bạn có bức tranh toàn cảnh (RAG Context và Knowledge Graph - Attack Surface).
2. Lập kế hoạch 1-3 bước tiếp theo để giải quyết yêu cầu của User.
3. Với mỗi bước, phân công rõ ràng cho "Recon Agent" hoặc "Exploit Agent".
4. Nếu đã đủ bằng chứng, hãy tổng hợp và đưa ra [CONCLUSION] và [SUMMARY].

QUY TẮC QUAN TRỌNG:
- Recon Agent CHỈ có: curl_http_check, nmap_scan_ports, nmap_scan, dirb_web_scan (với các mục tiêu là SPA/JS, hãy chỉ định wordlist='/usr/share/dirb/wordlists/big.txt' để tìm API), whatweb_fingerprint, nikto_web_scan, dnsrecon_lookup, wafw00f_waf_detect, graphql_introspection_check
- Exploit Agent CHỈ có: sqlmap_web_scan, commix_cmd_inject, hydra_brute_force, wfuzz_web_fuzz, zap_web_scan, zap_active_scan, zap_ajax_spider, curl_http_check
- MỖI BƯỚC phải ghi rõ: (a) tool nào cần gọi, (b) URL/tham số cụ thể, (c) mục đích của bước đó
- KHÔNG viết bước chung chung. VD sai: "Kiểm tra endpoint". VD đúng: "Dùng curl_http_check GET http://localhost:13000/rest/products/search?q=' để kiểm tra lỗi SQL"

QUY TẮC ĐẶC BIỆT CHO SQL INJECTION (WSTG-INPV-05):
- TUYỆT ĐỐI KHÔNG BAO GIỜ chạy sqlmap_web_scan trên trang chủ (ví dụ: http://localhost:13000). Trang chủ KHÔNG có tham số → sqlmap sẽ luôn trả về "không tìm thấy lỗ hổng".
- Bước 1 BẮT BUỘC: Dùng Recon Agent (curl_http_check) để thăm dò các API endpoint CÓ THAM SỐ TRUY VẤN. Các endpoint phổ biến cần thử:
  * http://localhost:13000/rest/products/search?q=test
  * http://localhost:13000/rest/user/login (POST với body {"email":"test","password":"test"})
  * http://localhost:13000/api/Products?d=
- Bước 2: CHỈ SAU KHI tìm được endpoint có tham số, mới gọi Exploit Agent chạy sqlmap_web_scan với URL ĐẦY ĐỦ CÓ THAM SỐ (ví dụ: url="http://localhost:13000/rest/products/search?q=test").

FORMAT TRẢ VỀ NẾU CẦN CHẠY TASK:
[PLAN]
Step 1: <Mô tả chi tiết: tool + URL + mục đích> -> [ASSIGN: RECON]
Step 2: <Mô tả chi tiết: tool + URL + mục đích> -> [ASSIGN: EXPLOIT]

FORMAT TRẢ VỀ NẾU ĐÃ KẾT THÚC:
Khi tất cả các bước đã hoàn thành, hoặc bạn có đủ bằng chứng để kết luận, bạn BẮT BUỘC phải đưa ra phán quyết cuối cùng theo ĐÚNG định dạng sau (đảm bảo xuống dòng rõ ràng):

[CONCLUSION] PASS hoặc ISSUE hoặc NEEDS_REVIEW
[SUMMARY]
**1. Trạng thái kiểm thử:** (Giải thích ngắn gọn tại sao lại có kết luận này)
**2. Lỗ hổng phát hiện (nếu có):** (Liệt kê rõ tên lỗ hổng, mức độ nghiêm trọng. Nếu không có ghi "Không phát hiện")
**3. Bằng chứng (Evidence):** (Mô tả URL bị lỗi, payload đã dùng, hoặc trích dẫn ngắn từ output của tool)
**4. Đánh giá & Phân tích:** (Phân tích chuyên sâu về lỗ hổng hoặc cấu hình an toàn)
**5. Khuyến nghị (nếu có):** (Cách khắc phục lỗ hổng này)

Quy tắc phán quyết:
- PASS: Không tìm thấy lỗ hổng.
- ISSUE: Chắc chắn có lỗ hổng (có payload chứng minh).
- NEEDS_REVIEW: Cần kiểm tra thủ công thêm (ví dụ blind SQLi tốn thời gian, hoặc 403 Forbidden).
"""

    def __init__(self, client, session_id: str, dkg: DynamicKnowledgeGraph, rag_enhancer: RAGEnhancer):
        self.client = client
        self.session_id = session_id
        self.dkg = dkg
        self.rag_enhancer = rag_enhancer

    async def plan_and_execute(self, user_message: str, wstg_id: str, base_rag: str) -> str:
        """Quy trình Orchestration Multi-Agent chính."""
        
        print(f"\n{'='*60}")
        print(f"[MULTI-AGENT] === BẮT ĐẦU MULTI-AGENT cho {wstg_id} ===")
        print(f"{'='*60}")
        
        context = self.rag_enhancer.enrich_prompt(wstg_id, base_rag)
        attack_surface = self.dkg.generate_attack_surface()
        
        # Trích xuất URL mục tiêu bằng code Python (không phụ thuộc LLM)
        target_url = _extract_target_url(user_message)
        print(f"[MULTI-AGENT] 🎯 Target URL được trích xuất: {target_url}")
        
        target_hint = f"\n\n[MỤC TIÊU PENTEST]: URL = {target_url}" if target_url else ""
        full_system = f"{self.SYSTEM_PROMPT}\n\n[HỆ THỐNG RAG VÀ GỢI Ý]\n{context}\n\n{attack_surface}{target_hint}"
        
        from app.config import settings
        
        messages = [
            {"role": "user", "content": full_system},
            {"role": "user", "content": f"Yêu cầu của người dùng: {user_message}\nMỤC TIÊU: {target_url}\nHãy lên kế hoạch (tối đa 3 bước) hoặc đưa ra kết luận nếu đã đủ thông tin."}
        ]
        
        recon_agent = ReconAgent(self.client, self.session_id, self.dkg, target_url=target_url)
        exploit_agent = ExploitAgent(self.client, self.session_id, self.dkg, target_url=target_url)
        verifier = Verifier(self.client)
        
        max_iterations = 3
        iteration = 0
        final_text = "Không có kết luận."
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n[MULTI-AGENT] 🧠 Planner đang lập kế hoạch (Vòng {iteration}/{max_iterations})...")
            
            resp = await self.client.generate_content(model=settings.openai_model, messages=messages)
            plan_text = resp.choices[0].message.content or ""
            
            # Nếu Planner đã đủ thông tin → kết luận ngay
            if "[CONCLUSION]" in plan_text:
                print(f"[MULTI-AGENT] 🧠 Planner kết luận ngay (đủ thông tin)")
                final_text = plan_text
                break
                
            # Parse steps từ plan (chấp nhận cả -> [ASSIGN: RECON] hoặc * ASSIGN: RECON)
            steps = re.findall(r'Step \d+:(.*?)(?:->)?\s*\*?\s*\[?ASSIGN:\s*(RECON|EXPLOIT)\]?', plan_text, re.IGNORECASE | re.DOTALL)
            
            if not steps:
                print(f"[MULTI-AGENT] ❌ Không parse được steps từ plan")
                print(f"[MULTI-AGENT] Plan text: {plan_text[:300]}...")
                final_text = "Planner không thể lập kế hoạch hợp lệ.\n\n" + plan_text
                break
            
            print(f"[MULTI-AGENT] 🧠 Planner trả về {len(steps)} bước")
            for i, (desc, assignee) in enumerate(steps):
                print(f"[MULTI-AGENT]   Step {i+1}: [{assignee.upper()}] {desc.strip()[:100]}...")
            
            # Thực thi từng step
            results = []
            
            for i, (step_desc, assignee) in enumerate(steps):
                assignee = assignee.upper()
                step_desc_clean = step_desc.strip()
                
                print(f"\n[MULTI-AGENT] --- Step {i+1}/{len(steps)}: {assignee} ---")
                
                if assignee == "RECON":
                    step_result = await recon_agent.execute(step_desc_clean, wstg_id=wstg_id)
                elif assignee == "EXPLOIT":
                    step_result = await exploit_agent.execute(step_desc_clean, wstg_id=wstg_id)
                    
                    # VERIFICATION LOOP: Kiểm tra kết quả khai thác
                    vuln_keywords = ["vulnerability", "injection", "found", "exploitable", "sqli", "xss", "rce"]
                    if any(kw in step_result.lower() for kw in vuln_keywords):
                        print(f"[MULTI-AGENT] ⚡ Phát hiện từ khóa lỗ hổng → Gọi Verifier")
                        verdict = await verifier.verify(step_desc_clean, step_result)
                        
                        if verdict["verdict"] == "TRUE_POSITIVE" and verdict["confidence"] >= 70:
                            step_result += f"\n\n[VERIFIED]: ✅ Lỗ hổng đã được xác nhận (Confidence: {verdict['confidence']}%). Reason: {verdict['reason']}"
                        elif verdict["verdict"] == "FALSE_POSITIVE":
                            step_result += f"\n\n[VERIFIED]: ❌ CẢNH BÁO GIẢ (FALSE POSITIVE). Reason: {verdict['reason']}"
                        else:
                            step_result += f"\n\n[VERIFIED]: ⚠️ Cần xem xét thêm (INCONCLUSIVE). Reason: {verdict['reason']}"
                else:
                    continue
                    
                results.append(f"Kết quả {assignee} cho bước {i+1}:\n{step_result}")
            
            # Cập nhật context cho vòng lặp tiếp theo
            messages.append({"role": "model", "content": plan_text})
            
            if iteration == max_iterations:
                messages.append({"role": "user", "content": "Kết quả thực thi các bước:\n" + "\n\n".join(results) + "\n\nĐã đạt giới hạn vòng lặp. BẮT BUỘC: Bạn phải đưa ra [CONCLUSION] (PASS, ISSUE, hoặc NEEDS_REVIEW) và [SUMMARY]. KHÔNG ĐƯỢC đề xuất kế hoạch mới."})
                print(f"\n[MULTI-AGENT] 🧠 Planner đang tổng hợp kết quả (Vòng cuối)...")
                resp_final = await self.client.generate_content(model=settings.openai_model, messages=messages)
                final_text = resp_final.choices[0].message.content or "Không có kết luận."
            else:
                messages.append({"role": "user", "content": "Kết quả thực thi các bước:\n" + "\n\n".join(results) + "\n\nHãy phân tích kết quả. Nếu đã đủ thông tin, hãy đưa ra [CONCLUSION] và [SUMMARY]. Nếu chưa đủ, hãy đưa ra [PLAN] mới (Step 1, Step 2...) để tiếp tục điều tra."})

        print(f"[MULTI-AGENT] === KẾT THÚC MULTI-AGENT cho {wstg_id} ===\n")
        return final_text

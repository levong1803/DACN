from typing import List, Dict
from app.knowledge_graph import DynamicKnowledgeGraph

class RAGEnhancer:
    """Tăng cường RAG tĩnh bằng ngữ cảnh từ Dynamic Knowledge Graph."""
    
    def __init__(self, dkg: DynamicKnowledgeGraph):
        self.dkg = dkg
        # Mapping công nghệ → Gợi ý kỹ thuật tấn công
        self.TECH_ATTACK_MAP = {
            "mysql":    "Thử UNION SELECT, SLEEP(), BENCHMARK(). Dùng sqlmap với --dbms=mysql.",
            "postgres": "Thử UNION SELECT, pg_sleep(). Dùng sqlmap với --dbms=postgresql.",
            "sqlite":   "Thử UNION SELECT, typeof(), sqlite_version(). Dùng sqlmap với --dbms=sqlite.",
            "express":  "Kiểm tra prototype pollution, NoSQL injection (MongoDB), SSRF qua axios.",
            "apache":   "Kiểm tra mod_status (/server-status), .htaccess bypass, path traversal.",
            "nginx":    "Kiểm tra alias traversal, off-by-slash, proxy_pass SSRF.",
            "php":      "Kiểm tra LFI/RFI, type juggling, deserialization, eval injection.",
            "wordpress":"Kiểm tra xmlrpc.php, wp-admin brute force, plugin vulns (wpscan).",
            "nodejs":   "Kiểm tra Node.js deserialization, command injection qua eval() hoặc exec().",
            "graphql":  "Kiểm tra introspection query, field fuzzing, query batching attacks.",
            "jwt":      "Thử thay đổi thuật toán thành NONE, bruteforce secret key, check JWT signature bypass.",
            "mongodb":  "Thử NoSQL injection: $gt, $ne, $regex. Xem xét BSON injection."
        }
    
    def enrich_prompt(self, wstg_id: str, base_rag: str) -> str:
        """Bổ sung ngữ cảnh DKG vào RAG context truyền thống."""
        sections = [base_rag]
        
        # 1. Gợi ý tấn công theo công nghệ đã phát hiện
        tech_hints = self._get_tech_hints()
        if tech_hints:
            sections.append(f"\n[GỢI Ý TẤN CÔNG DỰA TRÊN CÔNG NGHỆ ĐÃ PHÁT HIỆN]\n{tech_hints}")
        
        # 2. Danh sách endpoint có sẵn (tự động tiêm vào không cần agent phải tìm lại)
        endpoints = self._get_dynamic_endpoints()
        if endpoints:
            sections.append(f"\n[DANH SÁCH ENDPOINT KHẢ DỤNG TRÊN HỆ THỐNG]\n{endpoints}")
        
        # 3. Lỗ hổng liên quan (nếu có)
        related_vulns = self._get_related_vulns(wstg_id)
        if related_vulns:
            sections.append(f"\n[CÁC LỖ HỔNG ĐÃ TÌM THẤY TRƯỚC ĐÓ]\n{related_vulns}")
            
        return "\n".join(sections)
    
    def _get_tech_hints(self) -> str:
        """Tìm tất cả technology/service nodes trong DKG → tra bảng TECH_ATTACK_MAP.
        Cũng quét legacy_cache summaries để phát hiện công nghệ từ raw output."""
        techs = self.dkg.find_nodes(node_type="service")
        techs += self.dkg.find_nodes(node_type="technology")
        
        hints = []
        found_techs = set()
        
        # 1. Từ DKG nodes
        for tech in techs:
            name = tech["label"].lower()
            if name in found_techs: continue
            
            for key, advice in self.TECH_ATTACK_MAP.items():
                if key in name:
                    hints.append(f"- **{tech['label']}**: {advice}")
                    found_techs.add(key)
                    break
        
        # 2. Từ legacy_cache raw text (whatweb, nmap, curl summaries)
        # Quét text thô để tìm tên công nghệ mà parser chưa bóc tách được
        scan_text = ""
        for cache_key, entry in self.dkg._legacy_cache.items():
            if isinstance(entry, dict):
                scan_text += " " + entry.get("summary", "")[:1000]
                scan_text += " " + entry.get("full_result", "")[:1000]
        
        scan_lower = scan_text.lower()
        import re as _re
        for key, advice in self.TECH_ATTACK_MAP.items():
            if key not in found_techs:
                # Dùng word boundary để tránh false positive (vd: 'php' match trong URL path)
                if _re.search(r'\b' + _re.escape(key) + r'\b', scan_lower):
                    hints.append(f"- **{key.capitalize()}** (phát hiện từ recon data): {advice}")
                    found_techs.add(key)
                    
        return "\n".join(hints) if hints else ""
    
    def _get_dynamic_endpoints(self) -> str:
        """Lấy danh sách endpoint từ DKG."""
        endpoints = self.dkg.find_nodes(node_type="endpoint")
        if not endpoints:
            return ""
            
        # Ưu tiên các endpoint có tham số (chứa '?') hoặc có vẻ là API
        def score(ep):
            s = 0
            label = ep.get("label", "")
            if "?" in label: s += 5
            if "api" in label.lower() or "rest" in label.lower(): s += 3
            if "login" in label.lower() or "admin" in label.lower(): s += 2
            return s
            
        prioritized = sorted(endpoints, key=score, reverse=True)
        
        lines = []
        for ep in prioritized[:20]:  # Giới hạn 20 endpoint để không tràn prompt
            method = ep.get("properties", {}).get("method", "GET/POST")
            lines.append(f"- {method} {ep['label']}")
            
        return "\n".join(lines)
    
    def _get_related_vulns(self, wstg_id: str) -> str:
        """Tìm các lỗ hổng đã phát hiện có liên quan đến category hiện tại."""
        category = wstg_id.split("-")[1] if "-" in wstg_id else ""
        vulns = self.dkg.find_nodes(node_type="vulnerability")
        if not vulns:
            return ""
            
        CATEGORY_VULN_MAP = {
            "INPV": ["injection", "xss", "sqli", "command_injection"],
            "ATHN": ["weak_password", "default_credentials", "brute_force"],
            "SESS": ["session_fixation", "cookie_manipulation"],
            "CONF": ["misconfiguration", "directory_listing", "default_config"],
        }
        
        relevant_types = CATEGORY_VULN_MAP.get(category, [])
        related = []
        for v in vulns:
            v_type = v.get("properties", {}).get("vuln_type", "").lower()
            if any(t in v_type for t in relevant_types) or not relevant_types:
                related.append(v)
                
        if not related:
            return ""
            
        lines = [f"- [{v['label']}] (phát hiện bởi: {', '.join(v.get('sources', []))})" for v in related[:10]]
        return "\n".join(lines)

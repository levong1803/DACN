import json
import threading
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
import datetime

class DynamicKnowledgeGraph:
    """Đồ thị tri thức động — thay thế flat JSON cache."""
    
    def __init__(self, cache_file: Path):
        self._nodes: Dict[str, Dict[str, Any]] = {}   # id -> node
        self._edges: List[Dict[str, Any]] = []         # list of edges
        self._lock = threading.Lock()
        self._file = cache_file
        # Tương thích ngược: lưu trữ raw results theo cache_key (giống hệ thống cũ)
        self._legacy_cache: Dict[str, Dict[str, Any]] = {}
        self.load()
    
    # ── CRUD Operations ──
    def add_node(self, node_type: str, label: str, properties: dict, source: str) -> str:
        """Thêm một node vào đồ thị. Trả về node_id."""
        node_id = f"{node_type}:{label}"
        with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = {
                    "id": node_id,
                    "type": node_type,
                    "label": label,
                    "properties": properties,
                    "sources": [source],
                    "created_at": datetime.datetime.utcnow().isoformat() + "Z"
                }
            else:
                # Update if already exists
                if source not in self._nodes[node_id]["sources"]:
                    self._nodes[node_id]["sources"].append(source)
                self._nodes[node_id]["properties"].update(properties)
            self._nodes[node_id]["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        return node_id
        
    def add_edge(self, from_id: str, to_id: str, relation: str, source: str) -> None:
        """Thêm một cạnh (liên kết) vào đồ thị."""
        with self._lock:
            # Check if edge already exists
            for edge in self._edges:
                if edge["from"] == from_id and edge["to"] == to_id and edge["relation"] == relation:
                    if source not in edge.get("sources", []):
                        edge.setdefault("sources", []).append(source)
                    return
            
            self._edges.append({
                "from": from_id,
                "to": to_id,
                "relation": relation,
                "sources": [source]
            })

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._nodes.get(node_id)
            
    def find_nodes(self, node_type: Optional[str] = None, **properties) -> List[Dict[str, Any]]:
        """Tìm các node theo type và thuộc tính."""
        result = []
        with self._lock:
            for node in self._nodes.values():
                if node_type and node.get("type") != node_type:
                    continue
                match = True
                for k, v in properties.items():
                    if node.get("properties", {}).get(k) != v:
                        match = False
                        break
                if match:
                    result.append(node)
        return result
        
    def get_neighbors(self, node_id: str, relation: Optional[str] = None) -> List[Dict[str, Any]]:
        """Tìm các node lân cận."""
        neighbors = []
        with self._lock:
            for edge in self._edges:
                if edge["from"] == node_id:
                    if relation and edge["relation"] != relation:
                        continue
                    if edge["to"] in self._nodes:
                        neighbors.append(self._nodes[edge["to"]])
        return neighbors

    # ── Parser Functions (thay thế _extract_*_summary) ──
    def ingest_nmap(self, raw_result: str, target: str) -> List[str]:
        """Parse nmap output → tạo nodes Host, Port, Service."""
        created = []
        host_id = self.add_node("host", target, {"scanner": "nmap"}, "nmap_scan")
        created.append(host_id)
        
        # Parse ports: "80/tcp  open  http  Apache httpd 2.4.49"
        for line in raw_result.split("\n"):
            match = re.match(r"(\d+)/([a-zA-Z]+)\s+open\s+(\S+)(?:\s+(.*))?", line.strip())
            if match:
                port, proto, service, version = match.groups()
                port_id = self.add_node("port", f"{port}/{proto}", 
                                        {"number": int(port), "protocol": proto}, "nmap_scan")
                self.add_edge(host_id, port_id, "has_port", "nmap_scan")
                
                svc_props = {}
                if version:
                    svc_props["version"] = version.strip()
                svc_id = self.add_node("service", service, svc_props, "nmap_scan")
                self.add_edge(port_id, svc_id, "runs_service", "nmap_scan")
                created.extend([port_id, svc_id])
                
        return created

    def ingest_dirb(self, raw_result: str, target: str) -> List[str]:
        """Parse dirb/ffuf output → tạo endpoint nodes."""
        created = []
        host_id = self.add_node("host", target, {}, "dirb_web_scan")
        
        urls = re.findall(r"(?:DIRECTORY|==> )?\s*(https?://[^\s]+)", raw_result)
        if urls:
            for url in set(urls):
                path = re.sub(r"https?://[^/]+", "", url)
                if not path:
                    path = "/"
                ep_id = self.add_node("endpoint", path, {"full_url": url}, "dirb_web_scan")
                self.add_edge(host_id, ep_id, "has_endpoint", "dirb_web_scan")
                created.append(ep_id)
        return created
        
    def ingest_curl(self, raw_result: str, url: str, method: str) -> List[str]:
        """Parse curl response."""
        path = re.sub(r"https?://[^/]+", "", url)
        if not path:
            path = "/"
        host_match = re.match(r"https?://([^/]+)", url)
        target = host_match.group(1) if host_match else "localhost"
        
        created = []
        host_id = self.add_node("host", target, {}, "curl_http_check")
        ep_id = self.add_node("endpoint", path, {"method": method}, "curl_http_check")
        self.add_edge(host_id, ep_id, "has_endpoint", "curl_http_check")
        created.append(ep_id)
        return created

    def ingest_whatweb(self, raw_result: str, target: str) -> List[str]:
        """Parse whatweb output → tạo technology nodes."""
        created = []
        host_id = self.add_node("host", target, {}, "whatweb_fingerprint")
        
        # Strip ANSI escape codes from WhatWeb's terminal output
        clean_result = re.sub(r'\x1b\[[0-9;]*m', '', raw_result)
        parts = re.split(r",\s*", clean_result.strip())
        for part in parts:
            if "[" in part and "]" in part:
                tech_name = part.split("[")[0].strip()
                if tech_name and len(tech_name) > 1 and tech_name not in ("Country", "HTTPServer", "IP", "Title", "http://localhost", "https://localhost") and not tech_name.startswith("http"):
                    tech_id = self.add_node("technology", tech_name, {}, "whatweb_fingerprint")
                    self.add_edge(host_id, tech_id, "uses_tech", "whatweb_fingerprint")
                    created.append(tech_id)
        return created

    # ── Deduplication ──
    def _dedup_vuln(self, endpoint: str, vuln_type: str, source: str) -> bool:
        """Kiểm tra xem lỗ hổng đã tồn tại chưa."""
        existing = self.find_nodes("vulnerability", endpoint=endpoint, vuln_type=vuln_type)
        if existing:
            node_id = existing[0]["id"]
            with self._lock:
                if source not in self._nodes[node_id]["sources"]:
                    self._nodes[node_id]["sources"].append(source)
            return True
        return False

    # ── Prompt Generation (thay thế get_recon_summary) ──
    def generate_context_summary(self, max_chars: int = 3000) -> str:
        """Tạo chuỗi summary từ Legacy Cache và DKG."""
        sections = []
        
        if "nmap_scan" in self._legacy_cache:
            nmap = self._legacy_cache["nmap_scan"].get("summary", "")
            if nmap: sections.append(f"[NMAP]\n{nmap}")
            
        if "whatweb_fingerprint" in self._legacy_cache:
            ww = self._legacy_cache["whatweb_fingerprint"].get("summary", "")
            if ww: sections.append(f"[WHATWEB]\n{ww}")
            
        if "dirb_web_scan" in self._legacy_cache:
            dirb = self._legacy_cache["dirb_web_scan"].get("summary", "")
            if dirb: sections.append(f"[DIRB]\n{dirb}")
        
        curl_sections = []
        for key, entry in self._legacy_cache.items():
            if key.startswith("curl:") and entry.get("is_important"):
                meth = entry.get("method", "GET")
                path = entry.get("path", "/")
                summary = entry.get("summary", "")
                if summary:
                    curl_sections.append(f"--- {meth} {path} ---\n{summary}")
        
        if curl_sections:
            sections.append("[CURL - CÁC ENDPOINT QUAN TRỌNG]\n" + "\n\n".join(curl_sections))
            
        full_text = "\n\n".join(sections)
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n... [CẮT BỚT DO DÀI]"
            
        return full_text

    def generate_attack_surface(self) -> str:
        """Tóm tắt bề mặt tấn công từ DKG."""
        lines = ["[BỀ MẶT TẤN CÔNG (Từ Knowledge Graph)]"]
        
        hosts = self.find_nodes("host")
        if not hosts:
            return ""
            
        for host in hosts:
            host_id = host["id"]
            lines.append(f"Host: {host['label']}")
            
            ports = self.get_neighbors(host_id, "has_port")
            if ports:
                port_list = []
                for p in ports:
                    svcs = self.get_neighbors(p["id"], "runs_service")
                    svc_names = [s["label"] for s in svcs]
                    port_list.append(f"{p['label']} ({', '.join(svc_names) if svc_names else 'unknown'})")
                lines.append(f" - Mở cổng: {', '.join(port_list)}")
                
            techs = self.get_neighbors(host_id, "uses_tech")
            if techs:
                lines.append(f" - Công nghệ: {', '.join([t['label'] for t in techs])}")
                
            endpoints = self.get_neighbors(host_id, "has_endpoint")
            if endpoints:
                lines.append(f" - Endpoints đã tìm thấy: {len(endpoints)} endpoints")
                for ep in endpoints[:15]:
                    lines.append(f"   * {ep['label']}")
                if len(endpoints) > 15:
                    lines.append(f"   * ... và {len(endpoints)-15} đường dẫn khác.")
                    
        return "\n".join(lines)

    # ── Persistence ──
    def save(self) -> None:
        with self._lock:
            data = {
                "nodes": self._nodes,
                "edges": self._edges,
                "legacy_cache": self._legacy_cache
            }
            try:
                self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[DKG] Error saving cache: {e}")

    def load(self) -> None:
        with self._lock:
            if not self._file.exists():
                return
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                if "nodes" not in data and "legacy_cache" not in data:
                    self._legacy_cache = data
                else:
                    self._nodes = data.get("nodes", {})
                    self._edges = data.get("edges", [])
                    self._legacy_cache = data.get("legacy_cache", {})
            except Exception as e:
                print(f"[DKG] Error loading cache: {e}")

    # ── Legacy Compatibility ──
    def get_cached_tool_result(self, tool_name: str, tool_args: dict) -> Optional[str]:
        cache_key = tool_name
        if tool_name == "curl_http_check":
            url = tool_args.get("url", "")
            method = tool_args.get("method", "GET")
            path = re.sub(r"https?://[^/]+", "", url)
            if not path: path = "/"
            cache_key = f"curl:{method}:{path}"
        elif tool_name == "nmap_scan_ports":
            cache_key = "nmap_scan"
            
        with self._lock:
            if cache_key in self._legacy_cache:
                return self._legacy_cache[cache_key].get("full_result")
        return None

    def save_legacy(self, cache_key: str, data: dict) -> bool:
        """Lưu vào legacy cache (để tương thích). Trả về True nếu thêm mới."""
        with self._lock:
            if cache_key in self._legacy_cache:
                return False
            self._legacy_cache[cache_key] = data
        return True

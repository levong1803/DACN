from app.recon_cache import _dkg

def migrate():
    print("Bắt đầu migrate dữ liệu cache sang Knowledge Graph...")
    count = 0
    
    # Duyệt qua các legacy entries
    for key, entry in list(_dkg._legacy_cache.items()):
        tool = entry.get("tool", "")
        result = entry.get("full_result", "")
        if not result:
            continue
            
        if "nmap" in tool:
            _dkg.ingest_nmap(result, "localhost:3000")
            count += 1
        elif "dirb" in tool:
            _dkg.ingest_dirb(result, "localhost:3000")
            count += 1
        elif "curl" in tool:
            path = entry.get("path", "/")
            method = entry.get("method", "GET")
            # Build full URL
            url = f"http://localhost:3000{path}"
            _dkg.ingest_curl(result, url, method)
            count += 1
        elif "whatweb" in tool:
            _dkg.ingest_whatweb(result, "localhost:3000")
            count += 1

    print(f"Migrate xong {count} entries.")
    _dkg.save()
    print("Trạng thái Graph mới:")
    print(f"- Nodes: {len(_dkg._nodes)}")
    print(f"- Edges: {len(_dkg._edges)}")

if __name__ == "__main__":
    migrate()

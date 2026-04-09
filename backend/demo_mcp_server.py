"""
MCP server (stdio): echo/time + nmap / dirb / hydra (nếu có trên PATH).
Đổi MCP_COMMAND / MCP_ARGS trong backend/.env sang Kali MCP đầy đủ nếu cần.

Biến môi trường (tùy chọn, set trước khi spawn process MCP — có thể export trong shell
hoặc cấu hình IDE):
  PENTEST_ALLOWED_HOSTS=host1,host2   — cho phép hostname/IP cụ thể (vd testphp.vulnweb.com)
  PENTEST_ALLOW_ANY=true              — bỏ kiểm tra phạm vi host (chỉ khi hợp pháp)
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from mcp.server.fastmcp import FastMCP

from pentest_mcp_tools import dirb_scan, hydra_http_get, nmap_scan, sqlmap_scan

mcp = FastMCP("Demo Pentest Tools")


@mcp.tool()
def echo(text: str) -> str:
    """Trả lại text — dùng để kiểm tra agent + MCP."""
    return text


@mcp.tool()
def server_time() -> str:
    """Trả về thời gian hiện tại trên server (ISO 8601)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@mcp.tool()
def nmap_scan_ports(target: str, ports: str = "80,443") -> str:
    """Quét cổng với nmap (cần cài nmap / Kali). Chỉ dùng trên mục tiêu được phép."""
    return nmap_scan(target, ports)


@mcp.tool()
def dirb_web_scan(url: str, wordlist: str | None = None) -> str:
    """Dò thư mục web với dirb. wordlist mặc định đường Kali; Windows cần chỉ đường file có sẵn."""
    return dirb_scan(url, wordlist)


@mcp.tool()
def hydra_http_login(
    host: str,
    port: int,
    username: str,
    password: str,
    path: str = "/",
) -> str:
    """Một cặp user/pass với hydra http-get — chỉ cho môi trường lab (DVWA, v.v.)."""
    return hydra_http_get(host, port, username, password, path)


@mcp.tool()
def sqlmap_web_scan(url: str, level: int = 1, risk: int = 1) -> str:
    """Quét và tìm lỗi cơ sở dữ liệu (SQL Injection) bằng sqlmap. Tham số level (1-5) và risk (1-3) có thể được tăng lên để quét sâu hơn nếu cần."""
    return sqlmap_scan(url, level, risk)


if __name__ == "__main__":
    mcp.run()

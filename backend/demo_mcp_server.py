"""
MCP server (stdio): echo/time + nmap / dirb / hydra / sqlmap + nikto / whatweb / wafw00f / dnsrecon / testssl / curl
(nếu có trên PATH).
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

from pentest_mcp_tools import (
    dirb_scan,
    hydra_brute,
    nmap_scan,
    sqlmap_scan,
    nikto_scan,
    whatweb_scan,
    wafw00f_detect,
    dnsrecon_scan,
    testssl_scan,
    curl_check,
    commix_scan,
    wfuzz_scan,
    tplmap_scan,
    zap_scan,
    reconng_scan,
    padbuster_scan,
)

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
def hydra_service_brute(
    host: str,
    service: str,
    username: str,
    password: str,
    port: int | None = None,
    extra: str = "",
) -> str:
    """Tấn công brute-force đa dịch vụ với hydra (http-get, http-post-form, ssh, ftp...). 
    Với http-post-form, tham số 'extra' cần định dạng: '/path:fields:F=failure_msg' (Vd: '/login.php:user=^USER^&pass=^PASS^:F=incorrect')."""
    return hydra_brute(host, service, username, password, port, extra)


@mcp.tool()
def sqlmap_web_scan(url: str, level: int = 1, risk: int = 1) -> str:
    """Quét và tìm lỗi cơ sở dữ liệu (SQL Injection) bằng sqlmap. Tham số level (1-5) và risk (1-3) có thể được tăng lên để quét sâu hơn nếu cần."""
    return sqlmap_scan(url, level, risk)


# ── 6 Tool mới ───────────────────────────────────────────────

@mcp.tool()
def nikto_web_scan(url: str, tuning: str = "") -> str:
    """Quét lỗ hổng web server toàn diện với nikto. Tuning: 1=Files, 2=Misconfigs, 3=Info Disclosure, 4=XSS, 5=Remote File, 6=DOS, 7=Remote Shell, 8=Command Exec, 9=SQL Injection."""
    return nikto_scan(url, tuning)


@mcp.tool()
def whatweb_fingerprint(target: str, aggression: int = 1) -> str:
    """Nhận diện công nghệ web (CMS, framework, server) với whatweb. Aggression: 1 (passive) đến 4 (aggressive)."""
    return whatweb_scan(target, aggression)


@mcp.tool()
def wafw00f_waf_detect(target: str) -> str:
    """Phát hiện Web Application Firewall (WAF) đang bảo vệ website với wafw00f."""
    return wafw00f_detect(target)


@mcp.tool()
def dnsrecon_lookup(domain: str, scan_type: str = "std") -> str:
    """Thu thập thông tin DNS (NS, MX, A, AAAA, SOA, TXT) với dnsrecon. scan_type: std (mặc định), brt (brute force subdomain), crt (cert transparency)."""
    return dnsrecon_scan(domain, scan_type)


@mcp.tool()
def testssl_check(target: str) -> str:
    """Kiểm tra cấu hình SSL/TLS toàn diện (cipher, protocol, certificate) với testssl.sh."""
    return testssl_scan(target)


@mcp.tool()
def curl_http_check(url: str, method: str = "HEAD") -> str:
    """Kiểm tra HTTP headers/response (HSTS, CSP, X-Frame-Options, cookies) với curl. Methods: HEAD, GET, OPTIONS."""
    return curl_check(url, method)


@mcp.tool()
def commix_cmd_inject(url: str) -> str:
    """Kiểm tra và khai thác lỗ hổng OS Command Injection tự động với commix. URL cần chứa tham số (VD: http://target/page.php?id=1)."""
    return commix_scan(url)


@mcp.tool()
def wfuzz_web_fuzz(url: str, wordlist: str = "/usr/share/wfuzz/wordlist/general/common.txt", hide_code: str = "404") -> str:
    """Fuzzing web (tìm file, thư mục, tham số ẩn) với wfuzz. Dùng FUZZ làm placeholder trong URL. Ẩn mã HTTP với hide_code (mặc định 404)."""
    return wfuzz_scan(url, wordlist, hide_code)


@mcp.tool()
def tplmap_ssti_scan(url: str) -> str:
    """Kiểm tra lỗ hổng Server-Side Template Injection (SSTI) với tplmap. URL cần chứa tham số để inject (VD: http://target/page?name=test)."""
    return tplmap_scan(url)


@mcp.tool()
def zap_web_scan(target: str, scan_type: str = "baseline") -> str:
    """Quét lỗ hổng web toàn diện với OWASP ZAP (headless). scan_type: 'baseline' (nhanh, passive) hoặc 'active' (sâu, chậm hơn). Phát hiện XSS, CSRF, Injection, Headers, Cookies và nhiều lỗ hổng khác."""
    return zap_scan(target, scan_type)


@mcp.tool()
def reconng_osint(domain: str, module: str = "recon/domains-hosts/hackertarget") -> str:
    """Thu thập thông tin OSINT (subdomains, hosts) với recon-ng. Modules phổ biến: recon/domains-hosts/hackertarget, recon/domains-hosts/certificate_transparency."""
    return reconng_scan(domain, module)


@mcp.tool()
def padbuster_oracle(url: str, encrypted_sample: str, block_size: int = 8) -> str:
    """Kiểm tra lỗ hổng Padding Oracle trên mã hóa CBC. Cần URL chứa encrypted value và mẫu encrypted_sample để thử."""
    return padbuster_scan(url, encrypted_sample, block_size)


if __name__ == "__main__":
    mcp.run()


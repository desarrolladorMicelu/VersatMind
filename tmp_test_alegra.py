"""Comprehensive test of all Alegra MCP auth/URL combinations"""
import httpx2, base64, json

token = "8bd83addb0947cad6691"
email = "tom@tomlampert.com"
basic = base64.b64encode(f"{email}:{token}".encode()).decode()
bearer_b64 = base64.b64encode(token.encode()).decode()

urls = [
    "https://mcp.alegra.com",
    "https://mcp.alegra.com/mcp",
    "https://api.alegra.com/api/v1/mcp",
]

payloads = [
    ("init v2025 clientInfo", {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","clientInfo":{"name":"t","version":"1"},"capabilities":{}}}),
    ("init v2025 client", {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","client":{"name":"t","version":"1"},"capabilities":{}}}),
    ("init v2026 client", {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28","client":{"name":"t","version":"1"},"capabilities":{}}}),
    ("tools/list", {"jsonrpc":"2.0","id":1,"method":"tools/list"}),
]

auths = [
    ("Basic email:token", {"Authorization": f"Basic {basic}"}),
    ("Bearer token", {"Authorization": f"Bearer {token}"}),
    ("Bearer b64(token)", {"Authorization": f"Bearer {bearer_b64}"}),
    ("No auth", {}),
]

for url in urls:
    for auth_name, auth_headers in auths:
        for payload_name, data in payloads:
            headers = dict(auth_headers)
            headers["content-type"] = "application/json"
            headers["accept"] = "application/json"
            # Also try with mcp-protocol-version header
            if "init" in payload_name:
                headers["mcp-protocol-version"] = "2025-03-26"
            try:
                r = httpx2.post(url, headers=headers, json=data, timeout=10)
                resp = r.text[:120]
                id_val = "null"
                try:
                    id_val = str(r.json().get("id", "?"))
                except Exception:
                    pass
                if r.status_code != 500 or "init" in payload_name:
                    print(f"{url:40s} | {auth_name:20s} | {payload_name:25s} | {r.status_code} id={id_val} {resp}")
            except Exception as e:
                print(f"{url:40s} | {auth_name:20s} | {payload_name:25s} | ERROR {type(e).__name__}")

# Summary: only print 500s briefly
print("\n--- Only successful or interesting results ---")
for url in urls:
    for auth_name, auth_headers in auths:
        for payload_name, data in payloads:
            headers = dict(auth_headers)
            headers["content-type"] = "application/json"
            if "init" in payload_name:
                headers["mcp-protocol-version"] = "2025-03-26"
            try:
                r = httpx2.post(url, headers=headers, json=data, timeout=10)
                if r.status_code != 500 and r.status_code != 404:
                    print(f"{url:40s} {auth_name:20s} {payload_name:25s} {r.status_code} {r.text[:120]}")
            except Exception:
                pass
"""Checks for the MCP server (api/mcp_server.py): stdio end to end, the HTTP mount behind a public Host header, and
the rate limit.

  uv run python -m api.test_mcp
"""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import main

fails = []
S204 = "ke/act/cap-63/part_II__chp_XVIII__subpart_nn_1__sec_204"


def expect(name, got, want):
    if got != want:
        fails.append((name, got, want))


async def stdio():
    params = StdioServerParameters(command=sys.executable, args=["-m", "api.mcp_server"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        names = sorted(t.name for t in (await s.list_tools()).tools)
        expect("six tools", len(names), 6)
        res = await s.call_tool("get_section", {"provision_id": S204})
        body = json.loads(res.content[0].text)
        expect("s.204 status present", bool(body.get("status")), True)
        expect("no ids over MCP", "ids" in body, False)


def http():
    from fastapi.testclient import TestClient
    with TestClient(main.app, base_url="https://api-production-0506.up.railway.app") as c:
        r = c.post("/mcp", headers={"accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        expect("public Host accepted", r.status_code, 200)
        expect("tools over HTTP", len(r.json()["result"]["tools"]), 6)
        expect("REST still served", c.get("/api/acts").status_code, 200)


def rate_limit():
    hits = {}
    expect("under limit", all(main.allow("ip", 0.0, hits) for _ in range(main.RATE)), True)
    expect("over limit", main.allow("ip", 1.0, hits), False)
    expect("other ip", main.allow("ip2", 1.0, hits), True)
    expect("window passes", main.allow("ip", main.WINDOW + 0.5, hits), True)


def run():
    expect("key: last entry", main.client_key("1.1.1.1, 2.2.2.2", "9.9.9.9"), "2.2.2.2")
    expect("key: peer fallback", main.client_key(None, "9.9.9.9"), "9.9.9.9")
    rate_limit()
    http()
    asyncio.run(stdio())
    for f in fails:
        print("FAIL", *f)
    print(f"{len(fails)} failures")
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    run()

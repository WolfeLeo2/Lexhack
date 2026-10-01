"""Hakiki's tools over MCP (the Model Context Protocol), for Claude and other AI clients.

  Remote: https://api-production-0506.up.railway.app/mcp   (mounted by api/main.py; streamable HTTP, stateless)
  Local:  uv run python -m api.mcp_server                   (stdio, e.g. Claude Desktop)

Read-only; every answer is what published sources say, not legal advice.
"""
import functools

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

INSTRUCTIONS = """Hakiki is a citator for Kenyan statutes: whether a section is in force, amended, repealed, or limited
or struck down by a court, with the court's verbatim words. A section's status is the status field get_section
returns; report it, never derive your own. Quote courts only from operative_quote, word for word. Hakiki holds ~10% of
judgments: a case not found is 'not in Hakiki's collection', never 'does not exist'. Say whether a ruling was checked
by a person or an AI reviewer (verified_by), and never present an unverified lead as the status. Report what the
sources say; this is not legal advice."""

mcp = MCPServer("hakiki", instructions=INSTRUCTIONS)
http_app = mcp.streamable_http_app(
    stateless_http=True, json_response=True, streamable_http_path="/mcp",
    # public, read-only, no cookies or auth: nothing for a DNS-rebinding attack to reach
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

# Import cycle: main mounts http_app at import, and tools imports main. mcp and http_app are defined above these
# imports so main finds them whichever module loads first (tools are listed per request, so registering later is fine).
from . import main, tools   # noqa: E402


def result_only(fn):
    @functools.wraps(fn)   # MCPServer reads the signature and docstring through __wrapped__
    def tool(*args, **kwargs):
        return fn(*args, **kwargs)["result"]
    return tool


for fn in tools.TOOLS.values():
    mcp.tool()(result_only(fn))

if __name__ == "__main__":
    from api import mcp_server as served   # this file runs as __main__; serve the copy main imported, so tools register once
    with main.POOL:
        served.mcp.run()   # stdio

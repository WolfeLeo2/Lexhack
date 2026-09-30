"""Hakiki's tools over MCP (the Model Context Protocol), for Claude and other AI clients.

  Remote: https://api-production-0506.up.railway.app/mcp   (mounted by api/main.py; streamable HTTP, stateless)
  Local:  uv run python -m api.mcp_server                   (stdio, e.g. Claude Desktop)

Read-only; every answer is what published sources say, not legal advice.
"""
import functools

from . import main   # first: main imports this module, so loading main first settles the import cycle
from . import tools

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

INSTRUCTIONS = """Hakiki is a citator for Kenyan statutes: whether a section is in force, amended, repealed, or limited
or struck down by a court, with the court's verbatim words. A section's status is the status field get_section
returns; report it, never derive your own. Quote courts only from operative_quote, word for word. Hakiki holds ~10% of
judgments: a case not found is 'not in Hakiki's collection', never 'does not exist'. Say whether a ruling was checked
by a person or an AI reviewer (verified_by), and never present an unverified lead as the status. Report what the
sources say; this is not legal advice."""

mcp = MCPServer("hakiki", instructions=INSTRUCTIONS)


def result_only(fn):
    @functools.wraps(fn)   # FastMCP reads the signature and docstring through __wrapped__
    def tool(*args, **kwargs):
        return fn(*args, **kwargs)["result"]
    return tool


for fn in tools.TOOLS.values():
    mcp.tool()(result_only(fn))

http_app = mcp.streamable_http_app(
    stateless_http=True, json_response=True, streamable_http_path="/mcp",
    # public, read-only, no cookies or auth: nothing for a DNS-rebinding attack to reach
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


if __name__ == "__main__":
    main.POOL.open()
    mcp.run()   # stdio

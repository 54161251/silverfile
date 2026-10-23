"""MCP server exposing SilverFile's deterministic tax tools (workstream P2).

Run standalone over stdio (what any MCP client, including the grader's, would connect to):

    python -m src.tools.mcp_server

The Computation agent calls the same server in-process (src/agents/computation.py), so the
numbers on the draft return come from MCP tool calls even when no separate process is running.

SDK compatibility: mcp 2.x renamed FastMCP to MCPServer (mcp.server.fastmcp no longer exists).
This module tries the 2.x names first and falls back to the 1.x names. requirements.txt pins
the version the team tested.
"""
import functools

from src.tools import tax_math

SERVER_NAME = "silverfile-tax-math"


def _sdk():
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server
        from mcp.server.fastmcp.exceptions import ToolError
    return Server, ToolError


def _as_tool(func, tool_error):
    """Wrap a tax_math function so its TaxMathError reaches the caller as a readable tool error."""
    @functools.wraps(func)
    def tool(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except tax_math.TaxMathError as exc:
            raise tool_error(str(exc)) from exc
    return tool


def build_server():
    """A new server with one tool per function in tax_math.TOOLS (name = dictionary key)."""
    Server, ToolError = _sdk()
    server = Server(SERVER_NAME)
    for name, func in tax_math.TOOLS.items():
        server.tool(name=name)(_as_tool(func, ToolError))
    return server


def main() -> None:
    build_server().run()  # stdio transport by default


if __name__ == "__main__":
    main()

"""python -m agent.mcp_server  -> stdio MCP server for Claude Desktop."""
from agent.mcp_server.server import build_server

if __name__ == "__main__":
    build_server().run(transport="stdio")

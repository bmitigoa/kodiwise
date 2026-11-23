"""python -m agent.mcp_server  -> stdio MCP server for Claude Desktop.

Local traces go to logs/traces.jsonl (KODIWISE_TRACE_FILE to move it, KODIWISE_TRACE=off to disable).
They hold tool names, timings, sizes and numbers only: no message text, phone numbers, emails or tokens.
"""
import os

from agent.core import telemetry
from agent.mcp_server.server import build_server

if __name__ == "__main__":
    if os.environ.get("KODIWISE_TRACE", "on").strip().lower() != "off":
        telemetry.configure_file()
    build_server().run(transport="stdio")

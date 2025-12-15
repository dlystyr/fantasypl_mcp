#!/usr/bin/env python
"""Fantasy Premier League MCP Server entry point."""

import asyncio
from src.fantasypl_mcp.server import run_server


def main():
    """Run the MCP server."""
    print("Starting Fantasy PL MCP Server...")
    asyncio.run(run_server())


if __name__ == "__main__":
    main()

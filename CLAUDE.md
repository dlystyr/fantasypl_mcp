# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based MCP (Model Context Protocol) server for Fantasy Premier League data and analytics. It connects to PostgreSQL (for data storage and analytics) and Redis (for caching), providing tools for FPL team analysis, transfer suggestions, and form insights.

## Development Setup

- Python version: 3.12.12
- Package manager: uv
- Virtual environment: `.venv/`

## Commands

```bash
# Install dependencies
uv sync

# Run the MCP server
uv run python main.py

# Sync FPL data (run manually or via cron)
uv run python scripts/sync_fpl_data.py
```

## Database Setup

Requires PostgreSQL and Redis running locally. Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
# Edit .env with your database credentials
```

## Architecture

```
fantasypl_mcp/
├── main.py                    # MCP server entry point
├── src/fantasypl_mcp/
│   ├── server.py              # MCP server with SSE transport
│   ├── config.py              # Pydantic settings
│   ├── fpl_client.py          # FPL API client
│   ├── tools/                 # MCP tool implementations
│   ├── database/              # PostgreSQL & Redis layer
│   └── analytics/             # Form, fixtures, insights
└── scripts/
    └── sync_fpl_data.py       # Cron job for data sync
```

## MCP Tools

- `get_player_info` - Get detailed player information
- `search_players` - Search players by name/team/position
- `get_team_form` - Team form analysis
- `get_fixture_difficulty` - Upcoming fixture difficulty
- `get_transfer_suggestions` - Transfer recommendations
- `analyze_my_team` - Analyze user's FPL team
- `get_captaincy_picks` - Captain suggestions
- `find_differentials` - Low-ownership picks
- `check_bogey_teams` - Historical opponent analysis

## Data Sync Schedule

- Weekdays: Twice daily (8am, 8pm)
- Weekends: Hourly

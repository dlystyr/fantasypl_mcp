"""MCP Server implementation with SSE transport."""

import asyncio
import json
from dataclasses import asdict

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.sse import SseServerTransport

from .config import get_settings
from .database.postgres import get_db, init_db
from .database.redis_cache import cache
from .database.models import Player, Team
from .analytics.form import (
    calculate_team_form,
    calculate_player_form,
    get_players_in_form,
    get_teams_in_form,
)
from .analytics.fixtures import (
    calculate_fixture_difficulty,
    get_player_fixture_difficulty,
    get_easiest_fixtures,
    identify_fixture_swings,
)
from .analytics.insights import (
    find_bogey_teams,
    find_favored_teams,
    generate_transfer_suggestions,
    find_differentials,
    get_captaincy_picks,
)
from .fpl_client import FPLClient

from sqlalchemy import select

settings = get_settings()

# Create MCP server instance
server = Server("fantasypl-mcp")


# Tool definitions
TOOLS = [
    Tool(
        name="get_player_info",
        description="Get detailed information about a specific player including stats, form, and availability",
        inputSchema={
            "type": "object",
            "properties": {
                "player_id": {
                    "type": "integer",
                    "description": "The FPL player ID"
                },
                "player_name": {
                    "type": "string",
                    "description": "Player name to search for (if ID not known)"
                }
            }
        }
    ),
    Tool(
        name="search_players",
        description="Search for players by name, team, or position",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (player name)"
                },
                "team": {
                    "type": "string",
                    "description": "Filter by team name"
                },
                "position": {
                    "type": "string",
                    "enum": ["GK", "DEF", "MID", "FWD"],
                    "description": "Filter by position"
                },
                "max_price": {
                    "type": "number",
                    "description": "Maximum price in millions (e.g., 8.5)"
                },
                "min_form": {
                    "type": "number",
                    "description": "Minimum form rating"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10)"
                }
            }
        }
    ),
    Tool(
        name="get_team_form",
        description="Get form analysis for a Premier League team based on recent results",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "integer",
                    "description": "The FPL team ID"
                },
                "team_name": {
                    "type": "string",
                    "description": "Team name to search for"
                },
                "last_n_games": {
                    "type": "integer",
                    "description": "Number of recent games to analyze (default 5)"
                }
            }
        }
    ),
    Tool(
        name="get_fixture_difficulty",
        description="Get upcoming fixture difficulty analysis for a team or player",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "integer",
                    "description": "The FPL team ID"
                },
                "player_id": {
                    "type": "integer",
                    "description": "The FPL player ID (will get their team's fixtures)"
                },
                "num_fixtures": {
                    "type": "integer",
                    "description": "Number of upcoming fixtures to analyze (default 5)"
                }
            }
        }
    ),
    Tool(
        name="get_transfer_suggestions",
        description="Get transfer recommendations based on form, fixtures, and budget",
        inputSchema={
            "type": "object",
            "properties": {
                "budget": {
                    "type": "number",
                    "description": "Maximum price in millions (e.g., 8.5)"
                },
                "position": {
                    "type": "string",
                    "enum": ["GK", "DEF", "MID", "FWD"],
                    "description": "Filter by position"
                },
                "exclude_players": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Player IDs to exclude (e.g., players you already own)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of suggestions (default 10)"
                }
            }
        }
    ),
    Tool(
        name="analyze_my_team",
        description="Analyze a user's FPL team by their team ID",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "integer",
                    "description": "The FPL team/entry ID (found in your team URL)"
                },
                "gameweek": {
                    "type": "integer",
                    "description": "Specific gameweek to analyze (default: current)"
                }
            },
            "required": ["team_id"]
        }
    ),
    Tool(
        name="get_captaincy_picks",
        description="Get captain suggestions for the upcoming gameweek",
        inputSchema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "integer",
                    "description": "Your FPL team ID to get suggestions from your squad"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of suggestions (default 5)"
                }
            }
        }
    ),
    Tool(
        name="find_differentials",
        description="Find low-ownership players with good potential",
        inputSchema={
            "type": "object",
            "properties": {
                "max_ownership": {
                    "type": "number",
                    "description": "Maximum ownership percentage (default 10)"
                },
                "min_form": {
                    "type": "number",
                    "description": "Minimum form rating (default 3)"
                },
                "budget": {
                    "type": "number",
                    "description": "Maximum price in millions"
                },
                "position": {
                    "type": "string",
                    "enum": ["GK", "DEF", "MID", "FWD"],
                    "description": "Filter by position"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)"
                }
            }
        }
    ),
    Tool(
        name="check_bogey_teams",
        description="Check a player's historical performance against specific opponents to find bogey teams",
        inputSchema={
            "type": "object",
            "properties": {
                "player_id": {
                    "type": "integer",
                    "description": "The FPL player ID"
                },
                "player_name": {
                    "type": "string",
                    "description": "Player name to search for"
                }
            }
        }
    ),
]


POSITION_MAP = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
POSITION_MAP_REVERSE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


@server.list_tools()
async def list_tools():
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    try:
        if name == "get_player_info":
            return await handle_get_player_info(arguments)
        elif name == "search_players":
            return await handle_search_players(arguments)
        elif name == "get_team_form":
            return await handle_get_team_form(arguments)
        elif name == "get_fixture_difficulty":
            return await handle_get_fixture_difficulty(arguments)
        elif name == "get_transfer_suggestions":
            return await handle_get_transfer_suggestions(arguments)
        elif name == "analyze_my_team":
            return await handle_analyze_my_team(arguments)
        elif name == "get_captaincy_picks":
            return await handle_get_captaincy_picks(arguments)
        elif name == "find_differentials":
            return await handle_find_differentials(arguments)
        elif name == "check_bogey_teams":
            return await handle_check_bogey_teams(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def handle_get_player_info(args: dict):
    """Get detailed player information."""
    async with get_db() as session:
        player_id = args.get("player_id")
        player_name = args.get("player_name")

        if not player_id and player_name:
            # Search by name
            result = await session.execute(
                select(Player)
                .where(Player.web_name.ilike(f"%{player_name}%"))
                .limit(1)
            )
            player = result.scalar_one_or_none()
            if player:
                player_id = player.id

        if not player_id:
            return [TextContent(type="text", text="Player not found. Please provide a valid player_id or player_name.")]

        # Get player with team
        result = await session.execute(
            select(Player, Team.name, Team.short_name)
            .join(Team, Player.team_id == Team.id)
            .where(Player.id == player_id)
        )
        row = result.one_or_none()
        if not row:
            return [TextContent(type="text", text=f"Player with ID {player_id} not found.")]

        player, team_name, team_short = row

        # Get form analysis
        form_analysis = await calculate_player_form(session, player_id, 5)

        # Get fixture difficulty
        fixture_analysis = await calculate_fixture_difficulty(session, player.team_id, 5)

        info = {
            "id": player.id,
            "name": f"{player.first_name} {player.second_name}",
            "web_name": player.web_name,
            "team": team_name,
            "team_short": team_short,
            "position": POSITION_MAP_REVERSE.get(player.element_type, "UNK"),
            "price": (player.now_cost or 0) / 10,
            "ownership": f"{player.selected_by_percent}%",
            "status": player.status,
            "news": player.news or "No news",
            "chance_of_playing": player.chance_of_playing_next_round,
            "season_stats": {
                "total_points": player.total_points,
                "form": player.form,
                "points_per_game": player.points_per_game,
                "minutes": player.minutes,
                "goals": player.goals_scored,
                "assists": player.assists,
                "clean_sheets": player.clean_sheets,
                "bonus": player.bonus,
            },
            "expected_stats": {
                "xG": player.expected_goals,
                "xA": player.expected_assists,
                "xGI": player.expected_goal_involvements,
            },
            "ict_index": {
                "influence": player.influence,
                "creativity": player.creativity,
                "threat": player.threat,
                "total": player.ict_index,
            },
        }

        if form_analysis:
            info["form_analysis"] = {
                "form_rating": form_analysis.form_rating,
                "trend": form_analysis.trend,
                "last_5_avg": form_analysis.avg_points,
                "recent_performances": form_analysis.recent_performances[:3],
            }

        if fixture_analysis:
            info["upcoming_fixtures"] = {
                "avg_difficulty": fixture_analysis.avg_difficulty,
                "rating": fixture_analysis.difficulty_rating,
                "next_5": [
                    {
                        "opponent": f.opponent_short_name,
                        "home": f.is_home,
                        "difficulty": f.calculated_difficulty,
                    }
                    for f in fixture_analysis.upcoming_fixtures[:5]
                ]
            }

        return [TextContent(type="text", text=json.dumps(info, indent=2))]


async def handle_search_players(args: dict):
    """Search for players."""
    async with get_db() as session:
        query = select(Player, Team.name).join(Team, Player.team_id == Team.id)

        if args.get("query"):
            query = query.where(Player.web_name.ilike(f"%{args['query']}%"))

        if args.get("team"):
            query = query.where(Team.name.ilike(f"%{args['team']}%"))

        if args.get("position"):
            pos_id = POSITION_MAP.get(args["position"])
            if pos_id:
                query = query.where(Player.element_type == pos_id)

        if args.get("max_price"):
            max_cost = int(args["max_price"] * 10)
            query = query.where(Player.now_cost <= max_cost)

        if args.get("min_form"):
            query = query.where(Player.form >= args["min_form"])

        query = query.order_by(Player.form.desc())
        limit = args.get("limit", 10)
        query = query.limit(limit)

        result = await session.execute(query)
        rows = result.all()

        players = []
        for player, team_name in rows:
            players.append({
                "id": player.id,
                "name": player.web_name,
                "team": team_name,
                "position": POSITION_MAP_REVERSE.get(player.element_type, "UNK"),
                "price": (player.now_cost or 0) / 10,
                "form": player.form,
                "total_points": player.total_points,
                "ownership": f"{player.selected_by_percent}%",
            })

        return [TextContent(type="text", text=json.dumps({"players": players, "count": len(players)}, indent=2))]


async def handle_get_team_form(args: dict):
    """Get team form analysis."""
    async with get_db() as session:
        team_id = args.get("team_id")
        team_name = args.get("team_name")

        if not team_id and team_name:
            result = await session.execute(
                select(Team).where(Team.name.ilike(f"%{team_name}%")).limit(1)
            )
            team = result.scalar_one_or_none()
            if team:
                team_id = team.id

        if not team_id:
            return [TextContent(type="text", text="Team not found.")]

        last_n = args.get("last_n_games", 5)
        form = await calculate_team_form(session, team_id, last_n)

        if not form:
            return [TextContent(type="text", text="Could not calculate form for this team.")]

        result = {
            "team": form.team_name,
            "last_n_games": form.last_n_games,
            "record": f"{form.wins}W-{form.draws}D-{form.losses}L",
            "points": form.points,
            "goals_scored": form.goals_scored,
            "goals_conceded": form.goals_conceded,
            "clean_sheets": form.clean_sheets,
            "form_rating": form.form_rating,
            "trend": form.trend,
            "recent_results": form.recent_results,
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_fixture_difficulty(args: dict):
    """Get fixture difficulty analysis."""
    async with get_db() as session:
        team_id = args.get("team_id")
        player_id = args.get("player_id")
        num_fixtures = args.get("num_fixtures", 5)

        if player_id:
            analysis = await get_player_fixture_difficulty(session, player_id, num_fixtures)
        elif team_id:
            analysis = await calculate_fixture_difficulty(session, team_id, num_fixtures)
        else:
            return [TextContent(type="text", text="Please provide team_id or player_id.")]

        if not analysis:
            return [TextContent(type="text", text="Could not analyze fixtures.")]

        result = {
            "team": analysis.team_name,
            "avg_difficulty": analysis.avg_difficulty,
            "difficulty_rating": analysis.difficulty_rating,
            "easy_fixtures": analysis.easy_fixtures,
            "hard_fixtures": analysis.hard_fixtures,
            "upcoming": [
                {
                    "gameweek": f.event,
                    "opponent": f.opponent_name,
                    "opponent_short": f.opponent_short_name,
                    "home": f.is_home,
                    "difficulty": f.calculated_difficulty,
                    "fpl_difficulty": f.fpl_difficulty,
                }
                for f in analysis.upcoming_fixtures
            ]
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_get_transfer_suggestions(args: dict):
    """Get transfer suggestions."""
    async with get_db() as session:
        position = None
        if args.get("position"):
            position = POSITION_MAP.get(args["position"])

        suggestions = await generate_transfer_suggestions(
            session,
            budget=args.get("budget"),
            position=position,
            exclude_player_ids=args.get("exclude_players"),
            limit=args.get("limit", 10),
        )

        result = [
            {
                "player_id": s.player_id,
                "name": s.player_name,
                "team": s.team_name,
                "position": s.position,
                "price": s.price,
                "form": s.form,
                "form_rating": s.form_rating,
                "fixture_difficulty": s.fixture_difficulty,
                "ownership": f"{s.ownership}%",
                "expected_points": s.expected_points,
                "reason": s.reason,
                "priority": s.priority,
            }
            for s in suggestions
        ]

        return [TextContent(type="text", text=json.dumps({"suggestions": result}, indent=2))]


async def handle_analyze_my_team(args: dict):
    """Analyze user's FPL team."""
    team_id = args.get("team_id")
    if not team_id:
        return [TextContent(type="text", text="Please provide your FPL team_id.")]

    try:
        async with FPLClient() as client:
            # Get team info
            entry = await client.get_entry(team_id)
            history = await client.get_entry_history(team_id)

            # Get current gameweek picks
            current_event = None
            for event in history.get("current", []):
                current_event = event["event"]

            if current_event:
                picks = await client.get_entry_picks(team_id, current_event)
            else:
                picks = {"picks": []}

            # Get player details for the squad
            player_ids = [p["element"] for p in picks.get("picks", [])]

            async with get_db() as session:
                squad_analysis = []
                for pick in picks.get("picks", []):
                    player_id = pick["element"]
                    result = await session.execute(
                        select(Player, Team.name)
                        .join(Team, Player.team_id == Team.id)
                        .where(Player.id == player_id)
                    )
                    row = result.one_or_none()
                    if row:
                        player, team_name = row
                        form_analysis = await calculate_player_form(session, player_id, 5)
                        fixture_analysis = await calculate_fixture_difficulty(session, player.team_id, 3)

                        squad_analysis.append({
                            "name": player.web_name,
                            "team": team_name,
                            "position": POSITION_MAP_REVERSE.get(player.element_type, "UNK"),
                            "is_captain": pick.get("is_captain", False),
                            "is_vice_captain": pick.get("is_vice_captain", False),
                            "multiplier": pick.get("multiplier", 1),
                            "form": player.form,
                            "form_rating": form_analysis.form_rating if form_analysis else 0,
                            "form_trend": form_analysis.trend if form_analysis else "unknown",
                            "fixture_difficulty": fixture_analysis.avg_difficulty if fixture_analysis else 5,
                            "fixture_rating": fixture_analysis.difficulty_rating if fixture_analysis else "unknown",
                            "status": player.status,
                            "news": player.news if player.news else None,
                        })

            analysis = {
                "team_name": entry.get("name"),
                "manager": f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}",
                "overall_rank": entry.get("summary_overall_rank"),
                "total_points": entry.get("summary_overall_points"),
                "gameweek_points": history.get("current", [{}])[-1].get("points") if history.get("current") else 0,
                "squad": squad_analysis,
                "concerns": [],
                "recommendations": [],
            }

            # Add concerns and recommendations
            for player in squad_analysis:
                if player["status"] != "a":
                    analysis["concerns"].append(f"{player['name']} is not fully available (status: {player['status']})")
                if player.get("news"):
                    analysis["concerns"].append(f"{player['name']}: {player['news']}")
                if player["form_trend"] == "declining":
                    analysis["concerns"].append(f"{player['name']} is in declining form")
                if player["fixture_rating"] == "hard":
                    analysis["recommendations"].append(f"Consider benching {player['name']} - tough fixtures ahead")

            return [TextContent(type="text", text=json.dumps(analysis, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error analyzing team: {str(e)}")]


async def handle_get_captaincy_picks(args: dict):
    """Get captain suggestions."""
    team_id = args.get("team_id")
    limit = args.get("limit", 5)

    player_ids = None
    if team_id:
        try:
            async with FPLClient() as client:
                history = await client.get_entry_history(team_id)
                current_event = history.get("current", [{}])[-1].get("event") if history.get("current") else None
                if current_event:
                    picks = await client.get_entry_picks(team_id, current_event)
                    player_ids = [p["element"] for p in picks.get("picks", [])]
        except Exception:
            pass

    async with get_db() as session:
        suggestions = await get_captaincy_picks(session, player_ids, limit)

        result = [
            {
                "player_id": s.player_id,
                "name": s.player_name,
                "team": s.team_name,
                "position": s.position,
                "form": s.form,
                "captain_score": s.form_rating,
                "fixture_difficulty": s.fixture_difficulty,
                "expected_points_as_captain": s.expected_points,
                "reason": s.reason,
            }
            for s in suggestions
        ]

        return [TextContent(type="text", text=json.dumps({"captain_picks": result}, indent=2))]


async def handle_find_differentials(args: dict):
    """Find differential players."""
    async with get_db() as session:
        position = None
        if args.get("position"):
            position = POSITION_MAP.get(args["position"])

        differentials = await find_differentials(
            session,
            max_ownership=args.get("max_ownership", 10.0),
            min_form=args.get("min_form", 3.0),
            budget=args.get("budget"),
            position=position,
            limit=args.get("limit", 10),
        )

        result = [
            {
                "player_id": d.player_id,
                "name": d.player_name,
                "team": d.team_name,
                "position": d.position,
                "price": d.price,
                "ownership": f"{d.ownership}%",
                "form": d.form,
                "total_points": d.total_points,
                "points_per_million": d.points_per_million,
                "fixture_difficulty": d.fixture_difficulty,
                "upside": d.upside_reason,
            }
            for d in differentials
        ]

        return [TextContent(type="text", text=json.dumps({"differentials": result}, indent=2))]


async def handle_check_bogey_teams(args: dict):
    """Check player's bogey teams."""
    async with get_db() as session:
        player_id = args.get("player_id")
        player_name = args.get("player_name")

        if not player_id and player_name:
            result = await session.execute(
                select(Player).where(Player.web_name.ilike(f"%{player_name}%")).limit(1)
            )
            player = result.scalar_one_or_none()
            if player:
                player_id = player.id

        if not player_id:
            return [TextContent(type="text", text="Player not found.")]

        bogey = await find_bogey_teams(session, player_id)
        favored = await find_favored_teams(session, player_id)

        result = {
            "player_id": player_id,
            "bogey_teams": [
                {
                    "opponent": b.opponent_name,
                    "games": b.games_played,
                    "avg_points": b.avg_points,
                    "overall_avg": b.overall_avg_points,
                    "difference": b.performance_diff,
                    "goals": b.goals,
                    "assists": b.assists,
                }
                for b in bogey[:5]
            ],
            "favored_teams": [
                {
                    "opponent": f.opponent_name,
                    "games": f.games_played,
                    "avg_points": f.avg_points,
                    "overall_avg": f.overall_avg_points,
                    "difference": f.performance_diff,
                    "goals": f.goals,
                    "assists": f.assists,
                }
                for f in favored[:5]
            ],
        }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run_server():
    """Run the MCP server with SSE transport."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse
    import uvicorn

    # Initialize database
    await init_db()

    # Connect to Redis
    await cache.connect()

    sse_transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    async def handle_messages(request):
        await sse_transport.handle_post_message(
            request.scope, request.receive, request._send
        )

    async def health_check(request):
        return JSONResponse({"status": "healthy", "server": "fantasypl-mcp"})

    app = Starlette(
        routes=[
            Route("/health", health_check),
            Route("/sse", handle_sse),
            Route("/messages/", handle_messages, methods=["POST"]),
        ]
    )

    config = uvicorn.Config(
        app,
        host=settings.server_host,
        port=settings.server_port,
        log_level="info",
    )
    server_instance = uvicorn.Server(config)
    await server_instance.serve()

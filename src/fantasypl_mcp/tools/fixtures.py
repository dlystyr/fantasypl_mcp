"""Fixture-related MCP tools."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..analytics.fixtures import (
    calculate_fixture_difficulty,
    get_player_fixture_difficulty,
    TeamFixtureAnalysis,
)


async def get_fixture_difficulty(
    session: AsyncSession,
    team_id: int | None = None,
    player_id: int | None = None,
    num_fixtures: int = 5
) -> dict | None:
    """Get fixture difficulty analysis."""
    if player_id:
        analysis = await get_player_fixture_difficulty(session, player_id, num_fixtures)
    elif team_id:
        analysis = await calculate_fixture_difficulty(session, team_id, num_fixtures)
    else:
        return None

    if not analysis:
        return None

    return {
        "team_id": analysis.team_id,
        "team_name": analysis.team_name,
        "avg_difficulty": analysis.avg_difficulty,
        "difficulty_rating": analysis.difficulty_rating,
        "easy_fixtures": analysis.easy_fixtures,
        "hard_fixtures": analysis.hard_fixtures,
        "upcoming_fixtures": [
            {
                "fixture_id": f.fixture_id,
                "event": f.event,
                "opponent_id": f.opponent_id,
                "opponent_name": f.opponent_name,
                "opponent_short": f.opponent_short_name,
                "is_home": f.is_home,
                "kickoff_time": f.kickoff_time.isoformat() if f.kickoff_time else None,
                "fpl_difficulty": f.fpl_difficulty,
                "calculated_difficulty": f.calculated_difficulty,
            }
            for f in analysis.upcoming_fixtures
        ]
    }

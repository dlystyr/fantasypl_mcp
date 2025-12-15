"""Team-related MCP tools."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Team
from ..analytics.form import calculate_team_form, TeamFormAnalysis


async def get_team_form(
    session: AsyncSession,
    team_id: int | None = None,
    team_name: str | None = None,
    last_n_games: int = 5
) -> dict | None:
    """Get team form analysis."""
    if not team_id and team_name:
        result = await session.execute(
            select(Team).where(Team.name.ilike(f"%{team_name}%")).limit(1)
        )
        team = result.scalar_one_or_none()
        if team:
            team_id = team.id

    if not team_id:
        return None

    form = await calculate_team_form(session, team_id, last_n_games)
    if not form:
        return None

    return {
        "team_id": form.team_id,
        "team_name": form.team_name,
        "last_n_games": form.last_n_games,
        "wins": form.wins,
        "draws": form.draws,
        "losses": form.losses,
        "goals_scored": form.goals_scored,
        "goals_conceded": form.goals_conceded,
        "clean_sheets": form.clean_sheets,
        "points": form.points,
        "form_rating": form.form_rating,
        "trend": form.trend,
        "recent_results": form.recent_results,
    }


async def analyze_my_team(
    session: AsyncSession,
    team_id: int,
    gameweek: int | None = None
) -> dict:
    """Analyze user's FPL team - placeholder for full implementation in server.py."""
    # This is implemented directly in server.py as it requires FPL API calls
    return {"error": "Use the full implementation in server.py"}

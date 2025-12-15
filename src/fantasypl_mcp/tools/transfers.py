"""Transfer and differential related MCP tools."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..analytics.insights import (
    generate_transfer_suggestions,
    find_differentials,
    get_captaincy_picks,
    find_bogey_teams,
    TransferSuggestion,
    DifferentialPlayer,
    BogeyTeamResult,
)


async def get_transfer_suggestions(
    session: AsyncSession,
    budget: float | None = None,
    position: int | None = None,
    exclude_player_ids: list[int] | None = None,
    limit: int = 10
) -> list[dict]:
    """Get transfer suggestions."""
    suggestions = await generate_transfer_suggestions(
        session,
        budget=budget,
        position=position,
        exclude_player_ids=exclude_player_ids,
        limit=limit,
    )

    return [
        {
            "player_id": s.player_id,
            "player_name": s.player_name,
            "team_name": s.team_name,
            "position": s.position,
            "price": s.price,
            "form": s.form,
            "form_rating": s.form_rating,
            "fixture_difficulty": s.fixture_difficulty,
            "ownership": s.ownership,
            "expected_points": s.expected_points,
            "reason": s.reason,
            "priority": s.priority,
        }
        for s in suggestions
    ]


async def get_captaincy_picks(
    session: AsyncSession,
    team_player_ids: list[int] | None = None,
    limit: int = 5
) -> list[dict]:
    """Get captain suggestions."""
    from ..analytics.insights import get_captaincy_picks as _get_captaincy_picks

    suggestions = await _get_captaincy_picks(session, team_player_ids, limit)

    return [
        {
            "player_id": s.player_id,
            "player_name": s.player_name,
            "team_name": s.team_name,
            "position": s.position,
            "form": s.form,
            "captain_score": s.form_rating,
            "fixture_difficulty": s.fixture_difficulty,
            "expected_points_as_captain": s.expected_points,
            "reason": s.reason,
        }
        for s in suggestions
    ]


async def find_differentials(
    session: AsyncSession,
    max_ownership: float = 10.0,
    min_form: float = 3.0,
    budget: float | None = None,
    position: int | None = None,
    limit: int = 10
) -> list[dict]:
    """Find differential players."""
    from ..analytics.insights import find_differentials as _find_differentials

    differentials = await _find_differentials(
        session,
        max_ownership=max_ownership,
        min_form=min_form,
        budget=budget,
        position=position,
        limit=limit,
    )

    return [
        {
            "player_id": d.player_id,
            "player_name": d.player_name,
            "team_name": d.team_name,
            "position": d.position,
            "price": d.price,
            "ownership": d.ownership,
            "form": d.form,
            "total_points": d.total_points,
            "points_per_million": d.points_per_million,
            "fixture_difficulty": d.fixture_difficulty,
            "upside_reason": d.upside_reason,
        }
        for d in differentials
    ]


async def check_bogey_teams(
    session: AsyncSession,
    player_id: int
) -> dict:
    """Check player's bogey and favored teams."""
    from ..analytics.insights import find_bogey_teams, find_favored_teams

    bogey = await find_bogey_teams(session, player_id)
    favored = await find_favored_teams(session, player_id)

    return {
        "player_id": player_id,
        "bogey_teams": [
            {
                "opponent_id": b.opponent_id,
                "opponent_name": b.opponent_name,
                "games_played": b.games_played,
                "avg_points": b.avg_points,
                "overall_avg_points": b.overall_avg_points,
                "performance_diff": b.performance_diff,
                "goals": b.goals,
                "assists": b.assists,
            }
            for b in bogey[:5]
        ],
        "favored_teams": [
            {
                "opponent_id": f.opponent_id,
                "opponent_name": f.opponent_name,
                "games_played": f.games_played,
                "avg_points": f.avg_points,
                "overall_avg_points": f.overall_avg_points,
                "performance_diff": f.performance_diff,
                "goals": f.goals,
                "assists": f.assists,
            }
            for f in favored[:5]
        ],
    }

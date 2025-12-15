"""Player-related MCP tools."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Player, Team
from ..analytics.form import calculate_player_form

POSITION_MAP_REVERSE = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


async def get_player_info(
    session: AsyncSession,
    player_id: int | None = None,
    player_name: str | None = None
) -> dict | None:
    """Get detailed player information."""
    if not player_id and player_name:
        result = await session.execute(
            select(Player)
            .where(Player.web_name.ilike(f"%{player_name}%"))
            .limit(1)
        )
        player = result.scalar_one_or_none()
        if player:
            player_id = player.id

    if not player_id:
        return None

    result = await session.execute(
        select(Player, Team.name, Team.short_name)
        .join(Team, Player.team_id == Team.id)
        .where(Player.id == player_id)
    )
    row = result.one_or_none()
    if not row:
        return None

    player, team_name, team_short = row
    form_analysis = await calculate_player_form(session, player_id, 5)

    return {
        "id": player.id,
        "name": f"{player.first_name} {player.second_name}",
        "web_name": player.web_name,
        "team": team_name,
        "team_short": team_short,
        "position": POSITION_MAP_REVERSE.get(player.element_type, "UNK"),
        "price": (player.now_cost or 0) / 10,
        "ownership": player.selected_by_percent,
        "status": player.status,
        "news": player.news,
        "form": player.form,
        "total_points": player.total_points,
        "form_analysis": {
            "form_rating": form_analysis.form_rating if form_analysis else 0,
            "trend": form_analysis.trend if form_analysis else "unknown",
        } if form_analysis else None,
    }


async def search_players(
    session: AsyncSession,
    query: str | None = None,
    team_name: str | None = None,
    position: int | None = None,
    max_cost: int | None = None,
    min_form: float | None = None,
    limit: int = 10
) -> list[dict]:
    """Search for players with filters."""
    stmt = select(Player, Team.name).join(Team, Player.team_id == Team.id)

    if query:
        stmt = stmt.where(Player.web_name.ilike(f"%{query}%"))

    if team_name:
        stmt = stmt.where(Team.name.ilike(f"%{team_name}%"))

    if position:
        stmt = stmt.where(Player.element_type == position)

    if max_cost:
        stmt = stmt.where(Player.now_cost <= max_cost)

    if min_form:
        stmt = stmt.where(Player.form >= min_form)

    stmt = stmt.order_by(Player.form.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "id": player.id,
            "name": player.web_name,
            "team": team,
            "position": POSITION_MAP_REVERSE.get(player.element_type, "UNK"),
            "price": (player.now_cost or 0) / 10,
            "form": player.form,
            "total_points": player.total_points,
            "ownership": player.selected_by_percent,
        }
        for player, team in rows
    ]

"""Advanced insights: bogey teams, transfer suggestions, differentials."""

from dataclasses import dataclass
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Player, Team, Fixture, PlayerHistory, Event
from .form import calculate_player_form, POSITION_MAP
from .fixtures import calculate_fixture_difficulty


@dataclass
class BogeyTeamResult:
    """Result of bogey team analysis."""
    player_id: int
    player_name: str
    opponent_id: int
    opponent_name: str
    games_played: int
    total_points: int
    avg_points: float
    goals: int
    assists: int
    overall_avg_points: float
    performance_diff: float  # Negative = worse against this team


@dataclass
class TransferSuggestion:
    """A transfer suggestion."""
    player_id: int
    player_name: str
    team_name: str
    position: str
    price: float
    form: float
    form_rating: float
    fixture_difficulty: float
    ownership: float
    expected_points: float
    reason: str
    priority: int  # 1 = highest


@dataclass
class DifferentialPlayer:
    """A differential (low-ownership) player pick."""
    player_id: int
    player_name: str
    team_name: str
    position: str
    price: float
    ownership: float
    form: float
    total_points: int
    points_per_million: float
    fixture_difficulty: float
    upside_reason: str


async def find_bogey_teams(
    session: AsyncSession,
    player_id: int,
    min_games: int = 2
) -> list[BogeyTeamResult]:
    """Find teams against which a player historically underperforms."""
    # Get player info
    player_result = await session.execute(
        select(Player).where(Player.id == player_id)
    )
    player = player_result.scalar_one_or_none()
    if not player:
        return []

    # Get all teams
    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    # Get player's overall average
    overall_result = await session.execute(
        select(func.avg(PlayerHistory.total_points))
        .where(PlayerHistory.player_id == player_id)
    )
    overall_avg = overall_result.scalar() or 0

    # Get performance against each opponent
    opponent_stats = await session.execute(
        select(
            PlayerHistory.opponent_team,
            func.count(PlayerHistory.id).label("games"),
            func.sum(PlayerHistory.total_points).label("total_points"),
            func.avg(PlayerHistory.total_points).label("avg_points"),
            func.sum(PlayerHistory.goals_scored).label("goals"),
            func.sum(PlayerHistory.assists).label("assists"),
        )
        .where(PlayerHistory.player_id == player_id)
        .group_by(PlayerHistory.opponent_team)
        .having(func.count(PlayerHistory.id) >= min_games)
    )

    bogey_teams = []
    for row in opponent_stats:
        opponent = teams_dict.get(row.opponent_team)
        if not opponent:
            continue

        avg_points = float(row.avg_points or 0)
        diff = avg_points - overall_avg

        # Only include if significantly worse than average
        if diff < -1.0:  # At least 1 point worse per game
            bogey_teams.append(BogeyTeamResult(
                player_id=player_id,
                player_name=player.web_name,
                opponent_id=row.opponent_team,
                opponent_name=opponent.name,
                games_played=row.games,
                total_points=row.total_points or 0,
                avg_points=round(avg_points, 2),
                goals=row.goals or 0,
                assists=row.assists or 0,
                overall_avg_points=round(overall_avg, 2),
                performance_diff=round(diff, 2),
            ))

    # Sort by performance difference (most negative first)
    bogey_teams.sort(key=lambda x: x.performance_diff)
    return bogey_teams


async def find_favored_teams(
    session: AsyncSession,
    player_id: int,
    min_games: int = 2
) -> list[BogeyTeamResult]:
    """Find teams against which a player historically overperforms."""
    player_result = await session.execute(
        select(Player).where(Player.id == player_id)
    )
    player = player_result.scalar_one_or_none()
    if not player:
        return []

    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    overall_result = await session.execute(
        select(func.avg(PlayerHistory.total_points))
        .where(PlayerHistory.player_id == player_id)
    )
    overall_avg = overall_result.scalar() or 0

    opponent_stats = await session.execute(
        select(
            PlayerHistory.opponent_team,
            func.count(PlayerHistory.id).label("games"),
            func.sum(PlayerHistory.total_points).label("total_points"),
            func.avg(PlayerHistory.total_points).label("avg_points"),
            func.sum(PlayerHistory.goals_scored).label("goals"),
            func.sum(PlayerHistory.assists).label("assists"),
        )
        .where(PlayerHistory.player_id == player_id)
        .group_by(PlayerHistory.opponent_team)
        .having(func.count(PlayerHistory.id) >= min_games)
    )

    favored_teams = []
    for row in opponent_stats:
        opponent = teams_dict.get(row.opponent_team)
        if not opponent:
            continue

        avg_points = float(row.avg_points or 0)
        diff = avg_points - overall_avg

        if diff > 1.0:  # At least 1 point better per game
            favored_teams.append(BogeyTeamResult(
                player_id=player_id,
                player_name=player.web_name,
                opponent_id=row.opponent_team,
                opponent_name=opponent.name,
                games_played=row.games,
                total_points=row.total_points or 0,
                avg_points=round(avg_points, 2),
                goals=row.goals or 0,
                assists=row.assists or 0,
                overall_avg_points=round(overall_avg, 2),
                performance_diff=round(diff, 2),
            ))

    favored_teams.sort(key=lambda x: x.performance_diff, reverse=True)
    return favored_teams


async def generate_transfer_suggestions(
    session: AsyncSession,
    budget: float | None = None,
    position: int | None = None,
    exclude_player_ids: list[int] | None = None,
    limit: int = 10
) -> list[TransferSuggestion]:
    """Generate transfer suggestions based on form and fixtures."""
    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    # Build query
    query = select(Player).where(
        and_(
            Player.status == "a",  # Available
            Player.minutes > 0,  # Has played
        )
    )

    if budget:
        max_cost = int(budget * 10)  # Convert to tenths
        query = query.where(Player.now_cost <= max_cost)

    if position:
        query = query.where(Player.element_type == position)

    if exclude_player_ids:
        query = query.where(~Player.id.in_(exclude_player_ids))

    # Order by form initially
    query = query.order_by(Player.form.desc()).limit(50)

    players_result = await session.execute(query)
    players = players_result.scalars().all()

    suggestions = []
    for player in players:
        team = teams_dict.get(player.team_id)
        if not team:
            continue

        # Get fixture difficulty
        fixture_analysis = await calculate_fixture_difficulty(session, player.team_id, 5)
        fixture_diff = fixture_analysis.avg_difficulty if fixture_analysis else 5.0

        # Get form analysis
        form_analysis = await calculate_player_form(session, player.id, 5)
        form_rating = form_analysis.form_rating if form_analysis else float(player.form or 0)

        # Calculate expected points (simple model)
        # Higher form + easier fixtures = more expected points
        base_expected = float(player.form or 0) * 1.5
        fixture_bonus = (5 - fixture_diff) * 0.3  # Easier fixtures = positive bonus
        expected_points = max(0, base_expected + fixture_bonus)

        # Determine reason
        reasons = []
        if form_rating >= 7:
            reasons.append("excellent form")
        elif form_rating >= 5:
            reasons.append("good form")

        if fixture_diff <= 3:
            reasons.append("very easy fixtures")
        elif fixture_diff <= 4.5:
            reasons.append("favorable fixtures")

        if player.selected_by_percent and player.selected_by_percent < 10:
            reasons.append("low ownership differential")

        if not reasons:
            reasons.append("solid option")

        # Calculate priority based on form and fixtures
        priority = 3  # Default medium
        if form_rating >= 7 and fixture_diff <= 4:
            priority = 1  # High priority
        elif form_rating >= 5 and fixture_diff <= 5:
            priority = 2  # Medium-high priority

        suggestions.append(TransferSuggestion(
            player_id=player.id,
            player_name=player.web_name,
            team_name=team.name,
            position=POSITION_MAP.get(player.element_type, "UNK"),
            price=(player.now_cost or 0) / 10,
            form=float(player.form or 0),
            form_rating=form_rating,
            fixture_difficulty=fixture_diff,
            ownership=float(player.selected_by_percent or 0),
            expected_points=round(expected_points, 2),
            reason=", ".join(reasons),
            priority=priority,
        ))

    # Sort by priority then expected points
    suggestions.sort(key=lambda x: (x.priority, -x.expected_points))
    return suggestions[:limit]


async def find_differentials(
    session: AsyncSession,
    max_ownership: float = 10.0,
    min_form: float = 3.0,
    budget: float | None = None,
    position: int | None = None,
    limit: int = 10
) -> list[DifferentialPlayer]:
    """Find low-ownership players with good potential."""
    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    query = select(Player).where(
        and_(
            Player.status == "a",
            Player.selected_by_percent <= max_ownership,
            Player.form >= min_form,
            Player.minutes > 0,
        )
    )

    if budget:
        max_cost = int(budget * 10)
        query = query.where(Player.now_cost <= max_cost)

    if position:
        query = query.where(Player.element_type == position)

    query = query.order_by(Player.form.desc()).limit(50)

    players_result = await session.execute(query)
    players = players_result.scalars().all()

    differentials = []
    for player in players:
        team = teams_dict.get(player.team_id)
        if not team:
            continue

        price = (player.now_cost or 50) / 10
        total_points = player.total_points or 0
        points_per_million = total_points / price if price > 0 else 0

        # Get fixture difficulty
        fixture_analysis = await calculate_fixture_difficulty(session, player.team_id, 5)
        fixture_diff = fixture_analysis.avg_difficulty if fixture_analysis else 5.0

        # Determine upside reason
        reasons = []
        if player.form and float(player.form) >= 5:
            reasons.append(f"in-form ({player.form})")
        if points_per_million > 15:
            reasons.append(f"great value ({round(points_per_million, 1)} pts/m)")
        if fixture_diff <= 4:
            reasons.append("easy upcoming fixtures")
        if player.ict_index and player.ict_index > 50:
            reasons.append(f"high ICT ({player.ict_index})")

        if not reasons:
            reasons.append("potential sleeper pick")

        differentials.append(DifferentialPlayer(
            player_id=player.id,
            player_name=player.web_name,
            team_name=team.name,
            position=POSITION_MAP.get(player.element_type, "UNK"),
            price=price,
            ownership=float(player.selected_by_percent or 0),
            form=float(player.form or 0),
            total_points=total_points,
            points_per_million=round(points_per_million, 2),
            fixture_difficulty=fixture_diff,
            upside_reason="; ".join(reasons),
        ))

    # Sort by form * inverse of ownership (reward low ownership + high form)
    differentials.sort(
        key=lambda x: x.form * (1 / max(x.ownership, 0.1)),
        reverse=True
    )
    return differentials[:limit]


async def get_captaincy_picks(
    session: AsyncSession,
    team_player_ids: list[int] | None = None,
    limit: int = 5
) -> list[TransferSuggestion]:
    """Get captain suggestions for the upcoming gameweek."""
    # If team players provided, filter to those
    if team_player_ids:
        players_result = await session.execute(
            select(Player).where(Player.id.in_(team_player_ids))
        )
    else:
        # Get top form players
        players_result = await session.execute(
            select(Player)
            .where(and_(Player.status == "a", Player.minutes > 0))
            .order_by(Player.form.desc())
            .limit(30)
        )

    players = players_result.scalars().all()

    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    candidates = []
    for player in players:
        team = teams_dict.get(player.team_id)
        if not team:
            continue

        # Get next fixture difficulty
        fixture_analysis = await calculate_fixture_difficulty(session, player.team_id, 1)
        if not fixture_analysis or not fixture_analysis.upcoming_fixtures:
            continue

        next_fixture = fixture_analysis.upcoming_fixtures[0]
        fixture_diff = next_fixture.calculated_difficulty

        # Captain score: form * (10 - fixture_difficulty)
        form = float(player.form or 0)
        captain_score = form * (10 - fixture_diff) / 10

        reasons = []
        if form >= 6:
            reasons.append(f"excellent form ({form})")
        if fixture_diff <= 3:
            reasons.append(f"easy fixture vs {next_fixture.opponent_short_name}")
        elif fixture_diff <= 5:
            reasons.append(f"moderate fixture vs {next_fixture.opponent_short_name}")

        if next_fixture.is_home:
            reasons.append("home advantage")
            captain_score *= 1.1

        candidates.append(TransferSuggestion(
            player_id=player.id,
            player_name=player.web_name,
            team_name=team.name,
            position=POSITION_MAP.get(player.element_type, "UNK"),
            price=(player.now_cost or 0) / 10,
            form=form,
            form_rating=captain_score,  # Repurposing this field for captain score
            fixture_difficulty=fixture_diff,
            ownership=float(player.selected_by_percent or 0),
            expected_points=round(captain_score * 2, 2),  # Rough expected with captaincy
            reason="; ".join(reasons) if reasons else "solid pick",
            priority=1,
        ))

    # Sort by captain score
    candidates.sort(key=lambda x: x.form_rating, reverse=True)
    return candidates[:limit]

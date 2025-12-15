"""Form analysis for teams and players."""

from dataclasses import dataclass
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Player, Team, Fixture, PlayerHistory


@dataclass
class TeamFormAnalysis:
    """Team form analysis result."""
    team_id: int
    team_name: str
    last_n_games: int
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    clean_sheets: int
    points: int
    form_rating: float  # 0-10 scale
    trend: str  # "improving", "stable", "declining"
    recent_results: list[dict]


@dataclass
class PlayerFormAnalysis:
    """Player form analysis result."""
    player_id: int
    player_name: str
    team_name: str
    position: str
    last_n_games: int
    total_points: int
    avg_points: float
    minutes: int
    goals: int
    assists: int
    clean_sheets: int
    bonus_points: int
    xg: float
    xa: float
    xgi: float
    form_rating: float  # 0-10 scale
    trend: str  # "improving", "stable", "declining"
    recent_performances: list[dict]


POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


async def calculate_team_form(
    session: AsyncSession,
    team_id: int,
    last_n_games: int = 5
) -> TeamFormAnalysis | None:
    """Calculate form analysis for a team based on recent results."""
    # Get team info
    team_result = await session.execute(
        select(Team).where(Team.id == team_id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        return None

    # Get last N finished fixtures for the team
    fixtures_result = await session.execute(
        select(Fixture)
        .where(
            and_(
                Fixture.finished == True,
                (Fixture.team_h == team_id) | (Fixture.team_a == team_id)
            )
        )
        .order_by(Fixture.kickoff_time.desc())
        .limit(last_n_games)
    )
    fixtures = fixtures_result.scalars().all()

    if not fixtures:
        return None

    # Calculate form metrics
    wins = draws = losses = 0
    goals_scored = goals_conceded = clean_sheets = 0
    recent_results = []
    points_progression = []

    for fixture in fixtures:
        is_home = fixture.team_h == team_id
        team_score = fixture.team_h_score if is_home else fixture.team_a_score
        opp_score = fixture.team_a_score if is_home else fixture.team_h_score
        opp_id = fixture.team_a if is_home else fixture.team_h

        if team_score is None or opp_score is None:
            continue

        goals_scored += team_score
        goals_conceded += opp_score

        if opp_score == 0:
            clean_sheets += 1

        # Determine result
        if team_score > opp_score:
            wins += 1
            result = "W"
            match_points = 3
        elif team_score == opp_score:
            draws += 1
            result = "D"
            match_points = 1
        else:
            losses += 1
            result = "L"
            match_points = 0

        points_progression.append(match_points)
        recent_results.append({
            "fixture_id": fixture.id,
            "opponent_id": opp_id,
            "home": is_home,
            "score": f"{team_score}-{opp_score}",
            "result": result,
            "points": match_points,
        })

    total_points = wins * 3 + draws
    games_played = wins + draws + losses

    if games_played == 0:
        return None

    # Calculate form rating (0-10 scale)
    # Based on: points per game (max 3), goals scored, goals conceded
    ppg = total_points / games_played
    form_rating = min(10, (ppg / 3) * 7 + (goals_scored / games_played) * 1.5 - (goals_conceded / games_played) * 0.5)
    form_rating = max(0, form_rating)

    # Calculate trend based on points progression
    if len(points_progression) >= 3:
        first_half = sum(points_progression[len(points_progression)//2:])
        second_half = sum(points_progression[:len(points_progression)//2])
        if second_half > first_half + 2:
            trend = "improving"
        elif first_half > second_half + 2:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return TeamFormAnalysis(
        team_id=team_id,
        team_name=team.name,
        last_n_games=games_played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_scored=goals_scored,
        goals_conceded=goals_conceded,
        clean_sheets=clean_sheets,
        points=total_points,
        form_rating=round(form_rating, 2),
        trend=trend,
        recent_results=recent_results,
    )


async def calculate_player_form(
    session: AsyncSession,
    player_id: int,
    last_n_games: int = 5
) -> PlayerFormAnalysis | None:
    """Calculate form analysis for a player based on recent performances."""
    # Get player info with team
    player_result = await session.execute(
        select(Player, Team.name)
        .join(Team, Player.team_id == Team.id)
        .where(Player.id == player_id)
    )
    row = player_result.one_or_none()
    if not row:
        return None

    player, team_name = row

    # Get player's recent history
    history_result = await session.execute(
        select(PlayerHistory)
        .where(PlayerHistory.player_id == player_id)
        .order_by(PlayerHistory.event.desc())
        .limit(last_n_games)
    )
    history = history_result.scalars().all()

    if not history:
        # Fall back to current season stats if no history
        return PlayerFormAnalysis(
            player_id=player_id,
            player_name=player.web_name,
            team_name=team_name,
            position=POSITION_MAP.get(player.element_type, "UNK"),
            last_n_games=0,
            total_points=player.total_points or 0,
            avg_points=float(player.form or 0),
            minutes=player.minutes or 0,
            goals=player.goals_scored or 0,
            assists=player.assists or 0,
            clean_sheets=player.clean_sheets or 0,
            bonus_points=player.bonus or 0,
            xg=player.expected_goals or 0,
            xa=player.expected_assists or 0,
            xgi=player.expected_goal_involvements or 0,
            form_rating=min(10, float(player.form or 0)),
            trend="stable",
            recent_performances=[],
        )

    # Calculate metrics from history
    total_points = sum(h.total_points or 0 for h in history)
    minutes = sum(h.minutes or 0 for h in history)
    goals = sum(h.goals_scored or 0 for h in history)
    assists = sum(h.assists or 0 for h in history)
    clean_sheets = sum(h.clean_sheets or 0 for h in history)
    bonus_points = sum(h.bonus or 0 for h in history)
    xg = sum(h.expected_goals or 0 for h in history)
    xa = sum(h.expected_assists or 0 for h in history)
    xgi = sum(h.expected_goal_involvements or 0 for h in history)

    games_played = len(history)
    avg_points = total_points / games_played if games_played > 0 else 0

    # Recent performances
    recent_performances = []
    points_progression = []
    for h in history:
        recent_performances.append({
            "event": h.event,
            "opponent_id": h.opponent_team,
            "home": h.was_home,
            "points": h.total_points,
            "minutes": h.minutes,
            "goals": h.goals_scored,
            "assists": h.assists,
            "bonus": h.bonus,
            "xg": h.expected_goals,
            "xa": h.expected_assists,
        })
        points_progression.append(h.total_points or 0)

    # Calculate form rating based on position
    position = POSITION_MAP.get(player.element_type, "UNK")
    if position == "GK":
        # Goalkeepers: saves, clean sheets, points
        form_rating = min(10, avg_points * 1.2 + clean_sheets * 0.5)
    elif position == "DEF":
        # Defenders: clean sheets, goals/assists, points
        form_rating = min(10, avg_points * 1.0 + clean_sheets * 0.5 + (goals + assists) * 0.3)
    elif position == "MID":
        # Midfielders: goals, assists, points
        form_rating = min(10, avg_points * 0.8 + (goals + assists) * 0.5)
    else:  # FWD
        # Forwards: goals, xG performance, points
        form_rating = min(10, avg_points * 0.7 + goals * 0.8 + (xg - goals if goals < xg else 0) * 0.2)

    form_rating = max(0, form_rating)

    # Calculate trend
    if len(points_progression) >= 3:
        first_half = sum(points_progression[len(points_progression)//2:])
        second_half = sum(points_progression[:len(points_progression)//2])
        diff = second_half - first_half
        if diff > 5:
            trend = "improving"
        elif diff < -5:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return PlayerFormAnalysis(
        player_id=player_id,
        player_name=player.web_name,
        team_name=team_name,
        position=position,
        last_n_games=games_played,
        total_points=total_points,
        avg_points=round(avg_points, 2),
        minutes=minutes,
        goals=goals,
        assists=assists,
        clean_sheets=clean_sheets,
        bonus_points=bonus_points,
        xg=round(xg, 2),
        xa=round(xa, 2),
        xgi=round(xgi, 2),
        form_rating=round(form_rating, 2),
        trend=trend,
        recent_performances=recent_performances,
    )


async def get_players_in_form(
    session: AsyncSession,
    min_form: float = 5.0,
    position: int | None = None,
    max_cost: int | None = None,
    limit: int = 20
) -> list[Player]:
    """Get players currently in good form."""
    query = select(Player).where(Player.form >= min_form)

    if position:
        query = query.where(Player.element_type == position)

    if max_cost:
        query = query.where(Player.now_cost <= max_cost)

    query = query.order_by(Player.form.desc()).limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_teams_in_form(
    session: AsyncSession,
    last_n_games: int = 5,
    min_form_rating: float = 5.0
) -> list[TeamFormAnalysis]:
    """Get all teams ranked by form."""
    teams_result = await session.execute(select(Team))
    teams = teams_result.scalars().all()

    form_analyses = []
    for team in teams:
        analysis = await calculate_team_form(session, team.id, last_n_games)
        if analysis and analysis.form_rating >= min_form_rating:
            form_analyses.append(analysis)

    # Sort by form rating descending
    form_analyses.sort(key=lambda x: x.form_rating, reverse=True)
    return form_analyses

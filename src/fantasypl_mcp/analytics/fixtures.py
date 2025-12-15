"""Fixture difficulty analysis."""

from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Fixture, Team, Player


@dataclass
class FixtureDifficultyRating:
    """Rating for a single fixture."""
    fixture_id: int
    event: int
    opponent_id: int
    opponent_name: str
    opponent_short_name: str
    is_home: bool
    kickoff_time: datetime | None
    fpl_difficulty: int  # Original FPL difficulty (1-5)
    calculated_difficulty: float  # Our calculated difficulty (1-10)
    opponent_form_rating: float
    opponent_attack_strength: int
    opponent_defence_strength: int


@dataclass
class TeamFixtureAnalysis:
    """Fixture difficulty analysis for a team."""
    team_id: int
    team_name: str
    upcoming_fixtures: list[FixtureDifficultyRating]
    avg_difficulty: float
    difficulty_rating: str  # "easy", "moderate", "hard"
    easy_fixtures: int  # count of fixtures with difficulty <= 3
    hard_fixtures: int  # count of fixtures with difficulty >= 7


async def calculate_fixture_difficulty(
    session: AsyncSession,
    team_id: int,
    num_fixtures: int = 5
) -> TeamFixtureAnalysis | None:
    """Calculate fixture difficulty for upcoming games."""
    # Get team info
    team_result = await session.execute(
        select(Team).where(Team.id == team_id)
    )
    team = team_result.scalar_one_or_none()
    if not team:
        return None

    # Get upcoming fixtures
    fixtures_result = await session.execute(
        select(Fixture)
        .where(
            and_(
                Fixture.finished == False,
                (Fixture.team_h == team_id) | (Fixture.team_a == team_id)
            )
        )
        .order_by(Fixture.event)
        .limit(num_fixtures)
    )
    fixtures = fixtures_result.scalars().all()

    if not fixtures:
        return TeamFixtureAnalysis(
            team_id=team_id,
            team_name=team.name,
            upcoming_fixtures=[],
            avg_difficulty=0,
            difficulty_rating="unknown",
            easy_fixtures=0,
            hard_fixtures=0,
        )

    # Get all teams for opponent lookup
    teams_result = await session.execute(select(Team))
    teams_dict = {t.id: t for t in teams_result.scalars().all()}

    # Analyze each fixture
    upcoming = []
    for fixture in fixtures:
        is_home = fixture.team_h == team_id
        opponent_id = fixture.team_a if is_home else fixture.team_h
        opponent = teams_dict.get(opponent_id)

        if not opponent:
            continue

        # Get original FPL difficulty
        fpl_difficulty = fixture.team_h_difficulty if is_home else fixture.team_a_difficulty
        fpl_difficulty = fpl_difficulty or 3  # Default to medium

        # Calculate our own difficulty rating (1-10 scale)
        # Factors: FPL difficulty, opponent strength, home/away
        if is_home:
            opp_attack = opponent.strength_attack_away or 1000
            opp_defence = opponent.strength_defence_away or 1000
        else:
            opp_attack = opponent.strength_attack_home or 1000
            opp_defence = opponent.strength_defence_home or 1000

        # Normalize strength values (typically 900-1400 range)
        attack_factor = (opp_attack - 900) / 500  # 0-1 scale
        defence_factor = (opp_defence - 900) / 500  # 0-1 scale

        # Calculate difficulty
        base_difficulty = fpl_difficulty * 2  # Scale FPL 1-5 to 2-10
        strength_adjustment = (attack_factor + defence_factor) * 2 - 2  # -2 to +2
        home_adjustment = -0.5 if is_home else 0.5  # Home advantage

        calculated_difficulty = base_difficulty + strength_adjustment + home_adjustment
        calculated_difficulty = max(1, min(10, calculated_difficulty))

        # Simple form rating based on recent strength
        overall_strength = (opponent.strength_overall_home or 1000) if not is_home else (opponent.strength_overall_away or 1000)
        opponent_form_rating = (overall_strength - 900) / 50  # Rough approximation

        upcoming.append(FixtureDifficultyRating(
            fixture_id=fixture.id,
            event=fixture.event,
            opponent_id=opponent_id,
            opponent_name=opponent.name,
            opponent_short_name=opponent.short_name,
            is_home=is_home,
            kickoff_time=fixture.kickoff_time,
            fpl_difficulty=fpl_difficulty,
            calculated_difficulty=round(calculated_difficulty, 2),
            opponent_form_rating=round(opponent_form_rating, 2),
            opponent_attack_strength=opp_attack,
            opponent_defence_strength=opp_defence,
        ))

    # Calculate summary metrics
    if upcoming:
        avg_difficulty = sum(f.calculated_difficulty for f in upcoming) / len(upcoming)
        easy_fixtures = sum(1 for f in upcoming if f.calculated_difficulty <= 4)
        hard_fixtures = sum(1 for f in upcoming if f.calculated_difficulty >= 7)

        if avg_difficulty <= 4:
            difficulty_rating = "easy"
        elif avg_difficulty <= 6:
            difficulty_rating = "moderate"
        else:
            difficulty_rating = "hard"
    else:
        avg_difficulty = 0
        easy_fixtures = hard_fixtures = 0
        difficulty_rating = "unknown"

    return TeamFixtureAnalysis(
        team_id=team_id,
        team_name=team.name,
        upcoming_fixtures=upcoming,
        avg_difficulty=round(avg_difficulty, 2),
        difficulty_rating=difficulty_rating,
        easy_fixtures=easy_fixtures,
        hard_fixtures=hard_fixtures,
    )


async def get_player_fixture_difficulty(
    session: AsyncSession,
    player_id: int,
    num_fixtures: int = 5
) -> TeamFixtureAnalysis | None:
    """Get fixture difficulty for a player's team."""
    player_result = await session.execute(
        select(Player.team_id).where(Player.id == player_id)
    )
    team_id = player_result.scalar_one_or_none()

    if not team_id:
        return None

    return await calculate_fixture_difficulty(session, team_id, num_fixtures)


async def get_easiest_fixtures(
    session: AsyncSession,
    num_fixtures: int = 5,
    limit: int = 10
) -> list[TeamFixtureAnalysis]:
    """Get teams with the easiest upcoming fixtures."""
    teams_result = await session.execute(select(Team))
    teams = teams_result.scalars().all()

    analyses = []
    for team in teams:
        analysis = await calculate_fixture_difficulty(session, team.id, num_fixtures)
        if analysis and analysis.upcoming_fixtures:
            analyses.append(analysis)

    # Sort by average difficulty (ascending = easiest first)
    analyses.sort(key=lambda x: x.avg_difficulty)
    return analyses[:limit]


async def get_hardest_fixtures(
    session: AsyncSession,
    num_fixtures: int = 5,
    limit: int = 10
) -> list[TeamFixtureAnalysis]:
    """Get teams with the hardest upcoming fixtures."""
    analyses = await get_easiest_fixtures(session, num_fixtures, len((await session.execute(select(Team))).scalars().all()))
    # Reverse to get hardest first
    analyses.reverse()
    return analyses[:limit]


async def identify_fixture_swings(
    session: AsyncSession,
    num_fixtures: int = 6
) -> dict:
    """Identify teams with significant fixture difficulty changes."""
    teams_result = await session.execute(select(Team))
    teams = teams_result.scalars().all()

    swings = {
        "improving": [],  # Hard -> Easy
        "worsening": [],  # Easy -> Hard
    }

    for team in teams:
        analysis = await calculate_fixture_difficulty(session, team.id, num_fixtures)
        if not analysis or len(analysis.upcoming_fixtures) < 4:
            continue

        fixtures = analysis.upcoming_fixtures
        first_half = fixtures[:len(fixtures)//2]
        second_half = fixtures[len(fixtures)//2:]

        first_avg = sum(f.calculated_difficulty for f in first_half) / len(first_half)
        second_avg = sum(f.calculated_difficulty for f in second_half) / len(second_half)

        diff = first_avg - second_avg
        if diff > 2:  # Significant improvement
            swings["improving"].append({
                "team_id": team.id,
                "team_name": team.name,
                "current_difficulty": round(first_avg, 2),
                "future_difficulty": round(second_avg, 2),
                "change": round(diff, 2),
            })
        elif diff < -2:  # Significant worsening
            swings["worsening"].append({
                "team_id": team.id,
                "team_name": team.name,
                "current_difficulty": round(first_avg, 2),
                "future_difficulty": round(second_avg, 2),
                "change": round(diff, 2),
            })

    # Sort by magnitude of change
    swings["improving"].sort(key=lambda x: x["change"], reverse=True)
    swings["worsening"].sort(key=lambda x: x["change"])

    return swings

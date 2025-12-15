#!/usr/bin/env python
"""
Cron job script to sync FPL data from the API to the database.

Schedule:
- Weekdays: Twice daily at 8am and 8pm
- Weekends: Hourly

Example crontab:
    # Weekdays - twice daily at 8am and 8pm
    0 8,20 * * 1-5 cd /path/to/fantasypl_mcp && uv run python scripts/sync_fpl_data.py

    # Weekends - hourly
    0 * * * 0,6 cd /path/to/fantasypl_mcp && uv run python scripts/sync_fpl_data.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from fantasypl_mcp.fpl_client import FPLClient
from fantasypl_mcp.database.postgres import get_db, init_db
from fantasypl_mcp.database.redis_cache import cache
from fantasypl_mcp.database.models import (
    RawData,
    Team,
    Player,
    Fixture,
    PlayerHistory,
    Event,
)


async def upsert_teams(session, teams_data: list[dict]) -> None:
    """Upsert teams data into database."""
    for team in teams_data:
        stmt = insert(Team).values(
            id=team["id"],
            name=team["name"],
            short_name=team["short_name"],
            code=team["code"],
            strength=team.get("strength"),
            strength_overall_home=team.get("strength_overall_home"),
            strength_overall_away=team.get("strength_overall_away"),
            strength_attack_home=team.get("strength_attack_home"),
            strength_attack_away=team.get("strength_attack_away"),
            strength_defence_home=team.get("strength_defence_home"),
            strength_defence_away=team.get("strength_defence_away"),
            pulse_id=team.get("pulse_id"),
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": team["name"],
                "short_name": team["short_name"],
                "strength": team.get("strength"),
                "strength_overall_home": team.get("strength_overall_home"),
                "strength_overall_away": team.get("strength_overall_away"),
                "strength_attack_home": team.get("strength_attack_home"),
                "strength_attack_away": team.get("strength_attack_away"),
                "strength_defence_home": team.get("strength_defence_home"),
                "strength_defence_away": team.get("strength_defence_away"),
            }
        )
        await session.execute(stmt)


async def upsert_players(session, elements_data: list[dict]) -> None:
    """Upsert players data into database."""
    for player in elements_data:
        stmt = insert(Player).values(
            id=player["id"],
            code=player["code"],
            first_name=player.get("first_name"),
            second_name=player.get("second_name"),
            web_name=player["web_name"],
            team_id=player["team"],
            element_type=player["element_type"],
            now_cost=player.get("now_cost"),
            cost_change_start=player.get("cost_change_start"),
            cost_change_event=player.get("cost_change_event"),
            selected_by_percent=float(player.get("selected_by_percent", 0) or 0),
            form=float(player.get("form", 0) or 0),
            points_per_game=float(player.get("points_per_game", 0) or 0),
            total_points=player.get("total_points"),
            minutes=player.get("minutes"),
            goals_scored=player.get("goals_scored"),
            assists=player.get("assists"),
            clean_sheets=player.get("clean_sheets"),
            goals_conceded=player.get("goals_conceded"),
            own_goals=player.get("own_goals"),
            penalties_saved=player.get("penalties_saved"),
            penalties_missed=player.get("penalties_missed"),
            yellow_cards=player.get("yellow_cards"),
            red_cards=player.get("red_cards"),
            saves=player.get("saves"),
            bonus=player.get("bonus"),
            bps=player.get("bps"),
            expected_goals=float(player.get("expected_goals", 0) or 0),
            expected_assists=float(player.get("expected_assists", 0) or 0),
            expected_goal_involvements=float(player.get("expected_goal_involvements", 0) or 0),
            expected_goals_conceded=float(player.get("expected_goals_conceded", 0) or 0),
            influence=float(player.get("influence", 0) or 0),
            creativity=float(player.get("creativity", 0) or 0),
            threat=float(player.get("threat", 0) or 0),
            ict_index=float(player.get("ict_index", 0) or 0),
            status=player.get("status"),
            chance_of_playing_next_round=player.get("chance_of_playing_next_round"),
            chance_of_playing_this_round=player.get("chance_of_playing_this_round"),
            news=player.get("news"),
            news_added=datetime.fromisoformat(player["news_added"].replace("Z", "+00:00"))
            if player.get("news_added") else None,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "web_name": player["web_name"],
                "team_id": player["team"],
                "now_cost": player.get("now_cost"),
                "cost_change_event": player.get("cost_change_event"),
                "selected_by_percent": float(player.get("selected_by_percent", 0) or 0),
                "form": float(player.get("form", 0) or 0),
                "points_per_game": float(player.get("points_per_game", 0) or 0),
                "total_points": player.get("total_points"),
                "minutes": player.get("minutes"),
                "goals_scored": player.get("goals_scored"),
                "assists": player.get("assists"),
                "clean_sheets": player.get("clean_sheets"),
                "goals_conceded": player.get("goals_conceded"),
                "expected_goals": float(player.get("expected_goals", 0) or 0),
                "expected_assists": float(player.get("expected_assists", 0) or 0),
                "expected_goal_involvements": float(player.get("expected_goal_involvements", 0) or 0),
                "influence": float(player.get("influence", 0) or 0),
                "creativity": float(player.get("creativity", 0) or 0),
                "threat": float(player.get("threat", 0) or 0),
                "ict_index": float(player.get("ict_index", 0) or 0),
                "status": player.get("status"),
                "chance_of_playing_next_round": player.get("chance_of_playing_next_round"),
                "chance_of_playing_this_round": player.get("chance_of_playing_this_round"),
                "news": player.get("news"),
                "news_added": datetime.fromisoformat(player["news_added"].replace("Z", "+00:00"))
                if player.get("news_added") else None,
            }
        )
        await session.execute(stmt)


async def upsert_events(session, events_data: list[dict]) -> None:
    """Upsert events/gameweeks data into database."""
    for event in events_data:
        stmt = insert(Event).values(
            id=event["id"],
            name=event["name"],
            deadline_time=datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
            if event.get("deadline_time") else None,
            finished=event.get("finished", False),
            is_current=event.get("is_current", False),
            is_next=event.get("is_next", False),
            is_previous=event.get("is_previous", False),
            most_selected=event.get("most_selected"),
            most_transferred_in=event.get("most_transferred_in"),
            most_captained=event.get("most_captained"),
            most_vice_captained=event.get("most_vice_captained"),
            average_entry_score=event.get("average_entry_score"),
            highest_score=event.get("highest_score"),
            highest_scoring_entry=event.get("highest_scoring_entry"),
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "finished": event.get("finished", False),
                "is_current": event.get("is_current", False),
                "is_next": event.get("is_next", False),
                "is_previous": event.get("is_previous", False),
                "most_selected": event.get("most_selected"),
                "most_transferred_in": event.get("most_transferred_in"),
                "most_captained": event.get("most_captained"),
                "average_entry_score": event.get("average_entry_score"),
                "highest_score": event.get("highest_score"),
            }
        )
        await session.execute(stmt)


async def upsert_fixtures(session, fixtures_data: list[dict]) -> None:
    """Upsert fixtures data into database."""
    for fixture in fixtures_data:
        stmt = insert(Fixture).values(
            id=fixture["id"],
            code=fixture.get("code"),
            event=fixture.get("event"),
            team_h=fixture["team_h"],
            team_a=fixture["team_a"],
            team_h_score=fixture.get("team_h_score"),
            team_a_score=fixture.get("team_a_score"),
            finished=fixture.get("finished", False),
            finished_provisional=fixture.get("finished_provisional", False),
            kickoff_time=datetime.fromisoformat(fixture["kickoff_time"].replace("Z", "+00:00"))
            if fixture.get("kickoff_time") else None,
            minutes=fixture.get("minutes"),
            provisional_start_time=fixture.get("provisional_start_time", False),
            started=fixture.get("started", False),
            team_h_difficulty=fixture.get("team_h_difficulty"),
            team_a_difficulty=fixture.get("team_a_difficulty"),
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "event": fixture.get("event"),
                "team_h_score": fixture.get("team_h_score"),
                "team_a_score": fixture.get("team_a_score"),
                "finished": fixture.get("finished", False),
                "finished_provisional": fixture.get("finished_provisional", False),
                "kickoff_time": datetime.fromisoformat(fixture["kickoff_time"].replace("Z", "+00:00"))
                if fixture.get("kickoff_time") else None,
                "minutes": fixture.get("minutes"),
                "started": fixture.get("started", False),
            }
        )
        await session.execute(stmt)


async def sync_player_histories(
    session,
    fpl_client: FPLClient,
    top_n: int = 100
) -> None:
    """Sync player histories for top N players by total points."""
    # Get top players
    result = await session.execute(
        select(Player.id)
        .order_by(Player.total_points.desc())
        .limit(top_n)
    )
    player_ids = [row[0] for row in result.fetchall()]

    print(f"Syncing history for {len(player_ids)} top players...")

    for player_id in player_ids:
        try:
            summary = await fpl_client.get_element_summary(player_id)
            history = summary.get("history", [])

            for h in history:
                stmt = insert(PlayerHistory).values(
                    player_id=player_id,
                    fixture_id=h["fixture"],
                    event=h["round"],
                    opponent_team=h["opponent_team"],
                    was_home=h.get("was_home", False),
                    total_points=h.get("total_points"),
                    minutes=h.get("minutes"),
                    goals_scored=h.get("goals_scored"),
                    assists=h.get("assists"),
                    clean_sheets=h.get("clean_sheets"),
                    goals_conceded=h.get("goals_conceded"),
                    own_goals=h.get("own_goals"),
                    penalties_saved=h.get("penalties_saved"),
                    penalties_missed=h.get("penalties_missed"),
                    yellow_cards=h.get("yellow_cards"),
                    red_cards=h.get("red_cards"),
                    saves=h.get("saves"),
                    bonus=h.get("bonus"),
                    bps=h.get("bps"),
                    expected_goals=float(h.get("expected_goals", 0) or 0),
                    expected_assists=float(h.get("expected_assists", 0) or 0),
                    expected_goal_involvements=float(h.get("expected_goal_involvements", 0) or 0),
                    expected_goals_conceded=float(h.get("expected_goals_conceded", 0) or 0),
                    influence=float(h.get("influence", 0) or 0),
                    creativity=float(h.get("creativity", 0) or 0),
                    threat=float(h.get("threat", 0) or 0),
                    ict_index=float(h.get("ict_index", 0) or 0),
                    value=h.get("value"),
                    transfers_in=h.get("transfers_in"),
                    transfers_out=h.get("transfers_out"),
                    selected=h.get("selected"),
                ).on_conflict_do_nothing()
                await session.execute(stmt)

            # Cache the summary in Redis
            await cache.set_player_summary(player_id, summary)

            # Small delay to be nice to the API
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error syncing player {player_id}: {e}")
            continue


async def store_raw_data(session, data_type: str, data: dict | list) -> None:
    """Store raw API response as JSONB."""
    raw = RawData(
        data_type=data_type,
        data=data,
        fetched_at=datetime.utcnow(),
    )
    session.add(raw)


async def sync_all() -> None:
    """Main sync function to fetch and store all FPL data."""
    print(f"Starting FPL data sync at {datetime.utcnow()}")

    # Initialize database tables if needed
    await init_db()

    # Connect to Redis
    await cache.connect()

    try:
        async with FPLClient() as fpl_client:
            # Fetch bootstrap data
            print("Fetching bootstrap-static data...")
            bootstrap = await fpl_client.get_bootstrap_static()

            # Fetch fixtures
            print("Fetching fixtures...")
            fixtures = await fpl_client.get_fixtures()

            async with get_db() as session:
                # Store raw data
                print("Storing raw data...")
                await store_raw_data(session, "bootstrap", bootstrap)
                await store_raw_data(session, "fixtures", fixtures)

                # Upsert normalized data
                print("Upserting teams...")
                await upsert_teams(session, bootstrap.get("teams", []))

                print("Upserting events...")
                await upsert_events(session, bootstrap.get("events", []))

                print("Upserting players...")
                await upsert_players(session, bootstrap.get("elements", []))

                print("Upserting fixtures...")
                await upsert_fixtures(session, fixtures)

                # Sync player histories for top players
                print("Syncing player histories...")
                await sync_player_histories(session, fpl_client, top_n=100)

                await session.commit()

            # Update Redis cache
            print("Updating Redis cache...")
            await cache.set_bootstrap(bootstrap)

            # Cache upcoming fixtures
            upcoming = [f for f in fixtures if not f.get("finished")]
            await cache.set_upcoming_fixtures(upcoming)

        print(f"Sync completed successfully at {datetime.utcnow()}")

    except Exception as e:
        print(f"Sync failed: {e}")
        raise

    finally:
        await cache.disconnect()


if __name__ == "__main__":
    asyncio.run(sync_all())

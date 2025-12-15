"""SQLAlchemy models for FPL data."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# Use timezone-aware timestamps
TZDateTime = TIMESTAMP(timezone=True)


class RawData(Base):
    """Raw JSONB storage for API responses."""

    __tablename__ = "raw_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    data_type = Column(String(50), nullable=False, index=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(TZDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_raw_data_type_fetched", "data_type", "fetched_at"),
    )


class Team(Base):
    """Premier League teams."""

    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    short_name = Column(String(10), nullable=False)
    code = Column(Integer, nullable=False)
    strength = Column(Integer)
    strength_overall_home = Column(Integer)
    strength_overall_away = Column(Integer)
    strength_attack_home = Column(Integer)
    strength_attack_away = Column(Integer)
    strength_defence_home = Column(Integer)
    strength_defence_away = Column(Integer)
    pulse_id = Column(Integer)

    # Relationships
    players = relationship("Player", back_populates="team")
    home_fixtures = relationship(
        "Fixture",
        foreign_keys="Fixture.team_h",
        back_populates="home_team"
    )
    away_fixtures = relationship(
        "Fixture",
        foreign_keys="Fixture.team_a",
        back_populates="away_team"
    )


class Player(Base):
    """Player data."""

    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    code = Column(Integer, nullable=False)
    first_name = Column(String(100))
    second_name = Column(String(100))
    web_name = Column(String(100), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    element_type = Column(Integer, nullable=False)  # 1=GK, 2=DEF, 3=MID, 4=FWD

    # Current season stats
    now_cost = Column(Integer)  # Price in tenths (e.g., 100 = 10.0)
    cost_change_start = Column(Integer)
    cost_change_event = Column(Integer)
    selected_by_percent = Column(Float)
    form = Column(Float)
    points_per_game = Column(Float)
    total_points = Column(Integer)

    # Underlying stats
    minutes = Column(Integer)
    goals_scored = Column(Integer)
    assists = Column(Integer)
    clean_sheets = Column(Integer)
    goals_conceded = Column(Integer)
    own_goals = Column(Integer)
    penalties_saved = Column(Integer)
    penalties_missed = Column(Integer)
    yellow_cards = Column(Integer)
    red_cards = Column(Integer)
    saves = Column(Integer)
    bonus = Column(Integer)
    bps = Column(Integer)

    # Expected stats
    expected_goals = Column(Float)
    expected_assists = Column(Float)
    expected_goal_involvements = Column(Float)
    expected_goals_conceded = Column(Float)

    # ICT Index
    influence = Column(Float)
    creativity = Column(Float)
    threat = Column(Float)
    ict_index = Column(Float)

    # Availability
    status = Column(String(10))  # a=available, d=doubtful, i=injured, s=suspended, u=unavailable
    chance_of_playing_next_round = Column(Integer)
    chance_of_playing_this_round = Column(Integer)
    news = Column(Text)
    news_added = Column(TZDateTime)

    # Relationships
    team = relationship("Team", back_populates="players")
    history = relationship("PlayerHistory", back_populates="player")

    __table_args__ = (
        Index("ix_players_team_position", "team_id", "element_type"),
        Index("ix_players_form", "form"),
        Index("ix_players_total_points", "total_points"),
    )


class Fixture(Base):
    """All fixtures for the season."""

    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True)
    code = Column(Integer)
    event = Column(Integer, index=True)  # Gameweek number
    team_h = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team_a = Column(Integer, ForeignKey("teams.id"), nullable=False)
    team_h_score = Column(Integer)
    team_a_score = Column(Integer)
    finished = Column(Boolean, default=False)
    finished_provisional = Column(Boolean, default=False)
    kickoff_time = Column(TZDateTime, index=True)
    minutes = Column(Integer)
    provisional_start_time = Column(Boolean)
    started = Column(Boolean, default=False)

    # Difficulty ratings from FPL
    team_h_difficulty = Column(Integer)
    team_a_difficulty = Column(Integer)

    # Relationships
    home_team = relationship(
        "Team",
        foreign_keys=[team_h],
        back_populates="home_fixtures"
    )
    away_team = relationship(
        "Team",
        foreign_keys=[team_a],
        back_populates="away_fixtures"
    )

    __table_args__ = (
        Index("ix_fixtures_teams", "team_h", "team_a"),
        Index("ix_fixtures_event_finished", "event", "finished"),
    )


class PlayerHistory(Base):
    """Historical gameweek data per player."""

    __tablename__ = "player_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    event = Column(Integer, nullable=False)  # Gameweek
    opponent_team = Column(Integer, ForeignKey("teams.id"))
    was_home = Column(Boolean)

    # Performance stats
    total_points = Column(Integer)
    minutes = Column(Integer)
    goals_scored = Column(Integer)
    assists = Column(Integer)
    clean_sheets = Column(Integer)
    goals_conceded = Column(Integer)
    own_goals = Column(Integer)
    penalties_saved = Column(Integer)
    penalties_missed = Column(Integer)
    yellow_cards = Column(Integer)
    red_cards = Column(Integer)
    saves = Column(Integer)
    bonus = Column(Integer)
    bps = Column(Integer)

    # Expected stats
    expected_goals = Column(Float)
    expected_assists = Column(Float)
    expected_goal_involvements = Column(Float)
    expected_goals_conceded = Column(Float)

    # ICT
    influence = Column(Float)
    creativity = Column(Float)
    threat = Column(Float)
    ict_index = Column(Float)

    # Value
    value = Column(Integer)  # Price at that gameweek
    transfers_in = Column(Integer)
    transfers_out = Column(Integer)
    selected = Column(Integer)

    # Relationships
    player = relationship("Player", back_populates="history")

    __table_args__ = (
        Index("ix_player_history_player_event", "player_id", "event"),
        Index("ix_player_history_opponent", "opponent_team"),
    )


class Event(Base):
    """Gameweek/Event information."""

    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    deadline_time = Column(TZDateTime)
    finished = Column(Boolean, default=False)
    is_current = Column(Boolean, default=False)
    is_next = Column(Boolean, default=False)
    is_previous = Column(Boolean, default=False)

    # Chip stats
    most_selected = Column(Integer)  # Player ID
    most_transferred_in = Column(Integer)  # Player ID
    most_captained = Column(Integer)  # Player ID
    most_vice_captained = Column(Integer)  # Player ID

    # Averages
    average_entry_score = Column(Integer)
    highest_score = Column(Integer)
    highest_scoring_entry = Column(Integer)

    __table_args__ = (
        Index("ix_events_status", "is_current", "is_next"),
    )

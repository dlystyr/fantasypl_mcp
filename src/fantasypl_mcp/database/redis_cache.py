"""Valkey caching layer for FPL data (Redis-compatible)."""

import json
from typing import Any

import redis.asyncio as redis  # Works with Valkey (Redis-compatible)

from ..config import get_settings

settings = get_settings()


class ValkeyCache:
    """Valkey cache manager for FPL data."""

    # Cache key prefixes
    PREFIX_BOOTSTRAP = "fpl:bootstrap"
    PREFIX_PLAYER = "fpl:player"
    PREFIX_TEAM = "fpl:team"
    PREFIX_FIXTURES = "fpl:fixtures"
    PREFIX_FORM = "fpl:form"

    def __init__(self):
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Connect to Valkey."""
        self._client = redis.Redis.from_url(
            settings.valkey_url,
            decode_responses=True,
        )

    async def disconnect(self) -> None:
        """Disconnect from Valkey."""
        if self._client:
            await self._client.close()

    @property
    def client(self) -> redis.Redis:
        """Get Valkey client."""
        if not self._client:
            raise RuntimeError("Valkey not connected. Call connect() first.")
        return self._client

    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        value = await self.client.get(key)
        if value:
            return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> None:
        """Set value in cache with optional TTL."""
        serialized = json.dumps(value)
        if ttl:
            await self.client.setex(key, ttl, serialized)
        else:
            await self.client.set(key, serialized)

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        await self.client.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching pattern."""
        keys = await self.client.keys(pattern)
        if keys:
            await self.client.delete(*keys)

    # Bootstrap data
    async def get_bootstrap(self) -> dict | None:
        """Get cached bootstrap data."""
        return await self.get(f"{self.PREFIX_BOOTSTRAP}:latest")

    async def set_bootstrap(self, data: dict) -> None:
        """Cache bootstrap data."""
        await self.set(
            f"{self.PREFIX_BOOTSTRAP}:latest",
            data,
            ttl=settings.cache_ttl_bootstrap
        )

    # Player data
    async def get_player(self, player_id: int) -> dict | None:
        """Get cached player data."""
        return await self.get(f"{self.PREFIX_PLAYER}:{player_id}")

    async def set_player(self, player_id: int, data: dict) -> None:
        """Cache player data."""
        await self.set(
            f"{self.PREFIX_PLAYER}:{player_id}",
            data,
            ttl=settings.cache_ttl_player
        )

    async def get_player_summary(self, player_id: int) -> dict | None:
        """Get cached player summary (element-summary endpoint)."""
        return await self.get(f"{self.PREFIX_PLAYER}:{player_id}:summary")

    async def set_player_summary(self, player_id: int, data: dict) -> None:
        """Cache player summary."""
        await self.set(
            f"{self.PREFIX_PLAYER}:{player_id}:summary",
            data,
            ttl=settings.cache_ttl_player
        )

    # Team form
    async def get_team_form(self, team_id: int) -> dict | None:
        """Get cached team form analysis."""
        return await self.get(f"{self.PREFIX_FORM}:team:{team_id}")

    async def set_team_form(self, team_id: int, data: dict) -> None:
        """Cache team form analysis."""
        await self.set(
            f"{self.PREFIX_FORM}:team:{team_id}",
            data,
            ttl=settings.cache_ttl_bootstrap
        )

    # Player form
    async def get_player_form(self, player_id: int) -> dict | None:
        """Get cached player form analysis."""
        return await self.get(f"{self.PREFIX_FORM}:player:{player_id}")

    async def set_player_form(self, player_id: int, data: dict) -> None:
        """Cache player form analysis."""
        await self.set(
            f"{self.PREFIX_FORM}:player:{player_id}",
            data,
            ttl=settings.cache_ttl_player
        )

    # Upcoming fixtures
    async def get_upcoming_fixtures(self) -> list | None:
        """Get cached upcoming fixtures."""
        return await self.get(f"{self.PREFIX_FIXTURES}:upcoming")

    async def set_upcoming_fixtures(self, data: list) -> None:
        """Cache upcoming fixtures."""
        await self.set(
            f"{self.PREFIX_FIXTURES}:upcoming",
            data,
            ttl=settings.cache_ttl_fixtures
        )

    # Fixture difficulty
    async def get_fixture_difficulty(self, team_id: int, num_fixtures: int = 5) -> list | None:
        """Get cached fixture difficulty for a team."""
        return await self.get(f"{self.PREFIX_FIXTURES}:difficulty:{team_id}:{num_fixtures}")

    async def set_fixture_difficulty(
        self,
        team_id: int,
        data: list,
        num_fixtures: int = 5
    ) -> None:
        """Cache fixture difficulty."""
        await self.set(
            f"{self.PREFIX_FIXTURES}:difficulty:{team_id}:{num_fixtures}",
            data,
            ttl=settings.cache_ttl_fixtures
        )


# Global cache instance
cache = ValkeyCache()


async def get_cache() -> ValkeyCache:
    """Get cache instance."""
    return cache

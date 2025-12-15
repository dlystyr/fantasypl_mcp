"""FPL API client for fetching data from Fantasy Premier League."""

import httpx
from typing import Any

from .config import get_settings

settings = get_settings()


class FPLClient:
    """Client for interacting with the FPL API."""

    def __init__(self):
        self.base_url = settings.fpl_api_base_url
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FPLClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")
        return self._client

    async def get_bootstrap_static(self) -> dict[str, Any]:
        """Fetch bootstrap-static data (all players, teams, events)."""
        response = await self.client.get("/bootstrap-static/")
        response.raise_for_status()
        return response.json()

    async def get_fixtures(self) -> list[dict[str, Any]]:
        """Fetch all fixtures for the season."""
        response = await self.client.get("/fixtures/")
        response.raise_for_status()
        return response.json()

    async def get_element_summary(self, player_id: int) -> dict[str, Any]:
        """Fetch detailed player stats (history, fixtures)."""
        response = await self.client.get(f"/element-summary/{player_id}/")
        response.raise_for_status()
        return response.json()

    async def get_entry(self, team_id: int) -> dict[str, Any]:
        """Fetch user's team information."""
        response = await self.client.get(f"/entry/{team_id}/")
        response.raise_for_status()
        return response.json()

    async def get_entry_history(self, team_id: int) -> dict[str, Any]:
        """Fetch user's team history."""
        response = await self.client.get(f"/entry/{team_id}/history/")
        response.raise_for_status()
        return response.json()

    async def get_entry_picks(self, team_id: int, event_id: int) -> dict[str, Any]:
        """Fetch user's picks for a specific gameweek."""
        response = await self.client.get(f"/entry/{team_id}/event/{event_id}/picks/")
        response.raise_for_status()
        return response.json()

    async def get_entry_transfers(self, team_id: int) -> list[dict[str, Any]]:
        """Fetch user's transfer history."""
        response = await self.client.get(f"/entry/{team_id}/transfers/")
        response.raise_for_status()
        return response.json()

    async def get_event_live(self, event_id: int) -> dict[str, Any]:
        """Fetch live data for a gameweek."""
        response = await self.client.get(f"/event/{event_id}/live/")
        response.raise_for_status()
        return response.json()

    async def get_dream_team(self, event_id: int) -> dict[str, Any]:
        """Fetch dream team for a gameweek."""
        response = await self.client.get(f"/dream-team/{event_id}/")
        response.raise_for_status()
        return response.json()

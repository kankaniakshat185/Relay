"""Read-only Slack Web API calls."""

from typing import Any

import httpx

_API_BASE = "https://slack.com/api"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def list_channels(access_token: str, limit: int = 20) -> list[dict[str, Any]]:
    """Channels the bot has been added to — Slack only returns history for
    channels the bot is a member of, so this is naturally scoped to what
    the user actually granted, not every channel in the workspace."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/conversations.list",
            headers=_headers(access_token),
            params={
                "limit": limit,
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error (conversations.list): {data.get('error')}")
        channels: list[dict[str, Any]] = data["channels"]
        return channels


async def list_recent_messages(
    access_token: str, channel_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/conversations.history",
            headers=_headers(access_token),
            params={"channel": channel_id, "limit": limit},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error (conversations.history): {data.get('error')}")
        messages: list[dict[str, Any]] = data["messages"]
        return messages

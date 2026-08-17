"""Read-only GitHub REST API calls. No writes — matches the connector's
scope in plan.md §5, even though the OAuth `repo` scope itself permits more
(see `provider.py`)."""

from typing import Any

import httpx

_API_BASE = "https://api.github.com"


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_recent_repos(access_token: str, limit: int = 10) -> list[dict[str, Any]]:
    """Repos the authenticated user owns or collaborates on, most recently pushed first."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/user/repos",
            headers=_headers(access_token),
            params={"sort": "pushed", "direction": "desc", "per_page": limit},
        )
        response.raise_for_status()
        repos: list[dict[str, Any]] = response.json()
        return repos


async def list_recent_pull_requests(
    access_token: str, owner: str, repo: str, limit: int = 20
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls",
            headers=_headers(access_token),
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": limit},
        )
        response.raise_for_status()
        pulls: list[dict[str, Any]] = response.json()
        return pulls

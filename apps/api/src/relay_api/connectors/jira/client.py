"""Read-only Jira Cloud REST API v3 calls. `cloud_id` comes from the
`external_account_id` stored on the connector credential — see `provider.py`."""

from typing import Any

import httpx

_API_BASE = "https://api.atlassian.com/ex/jira"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


async def list_recent_issues(
    access_token: str, cloud_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/{cloud_id}/rest/api/3/search",
            headers=_headers(access_token),
            params={
                "jql": "ORDER BY updated DESC",
                "maxResults": limit,
                "fields": "summary,description,status,assignee,updated,issuetype",
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        issues: list[dict[str, Any]] = data["issues"]
        return issues

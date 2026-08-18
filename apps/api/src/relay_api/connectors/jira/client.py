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
    # Found live: Atlassian retired the old GET /rest/api/3/search endpoint
    # (410 Gone) in favor of POST /rest/api/3/search/jql — same issue
    # shape in the response, different request method/path. The new
    # endpoint also rejects a bare "ORDER BY" with no restriction
    # ("Unbounded JQL queries are not allowed here") — a 1-year bound
    # satisfies that *and* matches what "recent issues" should mean here,
    # consistent with GitHub/Slack only pulling recent activity too.
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{_API_BASE}/{cloud_id}/rest/api/3/search/jql",
            headers=_headers(access_token),
            json={
                "jql": "updated >= -365d ORDER BY updated DESC",
                "maxResults": limit,
                "fields": ["summary", "description", "status", "assignee", "updated", "issuetype"],
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        issues: list[dict[str, Any]] = data["issues"]
        return issues

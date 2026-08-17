"""Orchestrates GitHub client calls + normalization into the shape
`engine/ingestion` expects. Called by `jobs/indexing.py` — nothing else
should reach into `client.py`/`normalize.py` directly."""

from relay_api.connectors.github import client, normalize
from relay_api.engine.ingestion.schemas import NormalizedItem

_REPO_LIMIT = 10
_PR_LIMIT_PER_REPO = 20


async def fetch_normalized_items(access_token: str) -> list[NormalizedItem]:
    repos = await client.list_recent_repos(access_token, limit=_REPO_LIMIT)

    items: list[NormalizedItem] = []
    for repo in repos:
        prs = await client.list_recent_pull_requests(
            access_token, repo["owner"]["login"], repo["name"], limit=_PR_LIMIT_PER_REPO
        )
        items.extend(normalize.normalize_pull_request(pr, repo["full_name"]) for pr in prs)

    return items

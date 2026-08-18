"""Orchestrates GitHub client calls + normalization into the shape
`engine/ingestion` expects. Called by `jobs/indexing.py` — nothing else
should reach into `client.py`/`normalize.py` directly."""

from relay_api.connectors.github import client, normalize
from relay_api.engine.ingestion.schemas import NormalizedItem

_REPO_LIMIT = 10
_PR_LIMIT_PER_REPO = 20
_COMMIT_LIMIT_PER_REPO = 20


async def fetch_normalized_items(access_token: str) -> list[NormalizedItem]:
    repos = await client.list_recent_repos(access_token, limit=_REPO_LIMIT)

    items: list[NormalizedItem] = []
    for repo in repos:
        owner, name = repo["owner"]["login"], repo["name"]

        prs = await client.list_recent_pull_requests(
            access_token, owner, name, limit=_PR_LIMIT_PER_REPO
        )
        items.extend(normalize.normalize_pull_request(pr, repo["full_name"]) for pr in prs)

        commits = await client.list_recent_commits(
            access_token, owner, name, limit=_COMMIT_LIMIT_PER_REPO
        )
        items.extend(normalize.normalize_commit(commit, repo["full_name"]) for commit in commits)

    return items

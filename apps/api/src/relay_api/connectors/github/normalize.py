from datetime import datetime
from typing import Any

from relay_api.engine.ingestion.schemas import NormalizedItem


def normalize_pull_request(pr: dict[str, Any], repo_full_name: str) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=str(pr["id"]),
        title=pr["title"],
        body=pr.get("body") or "",
        url=pr["html_url"],
        author=(pr.get("user") or {}).get("login"),
        occurred_at=datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00")),
        extra={"repo": repo_full_name, "state": pr["state"], "number": pr["number"]},
    )


def normalize_commit(commit: dict[str, Any], repo_full_name: str) -> NormalizedItem:
    commit_data = commit["commit"]
    git_author = commit_data.get("author") or {}
    # `author` (linked GitHub account) may be null for commits from
    # emails GitHub can't match to a user — fall back to the raw git
    # author name in that case.
    github_user = commit.get("author") or {}

    message = commit_data.get("message", "")
    title = message.splitlines()[0] if message else "(no commit message)"

    return NormalizedItem(
        source="github",
        source_type="commit",
        external_id=commit["sha"],
        title=title,
        body=message,
        url=commit["html_url"],
        author=github_user.get("login") or git_author.get("name"),
        occurred_at=datetime.fromisoformat(git_author["date"].replace("Z", "+00:00")),
        extra={"repo": repo_full_name, "sha": commit["sha"][:7]},
    )

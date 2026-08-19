from datetime import datetime
from typing import Any

from relay_api.connectors.text_utils import truncate_title
from relay_api.engine.ingestion.schemas import NormalizedItem


def normalize_pull_request(pr: dict[str, Any], repo_full_name: str) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=str(pr["id"]),
        title=truncate_title(pr["title"]),
        body=pr.get("body") or "",
        url=pr["html_url"],
        author=(pr.get("user") or {}).get("login"),
        occurred_at=datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00")),
        extra={"repo": repo_full_name, "state": pr["state"], "number": pr["number"]},
    )


def normalize_review(
    review: dict[str, Any], repo_full_name: str, pr_number: int
) -> NormalizedItem | None:
    """One top-level review verdict on a PR. Returns `None` for a review
    with no body — a bare "Approve" click with no comment has nothing
    worth indexing, and would otherwise show up as an empty-excerpt entry
    everywhere `find_review_comments_for_pr` is used. `extra.pr_number` is
    the join key `engine.correlation.find_review_comments_for_pr` filters
    on directly, not something searched for semantically."""
    body = review.get("body") or ""
    if not body.strip():
        return None

    return NormalizedItem(
        source="github",
        source_type="review_comment",
        # Reviews and inline comments (below) share one source_type but
        # have separate id namespaces in GitHub's API — prefixed so they
        # can't collide as the same `external_id`.
        external_id=f"review-{review['id']}",
        title=truncate_title(f"Review: {review['state']}"),
        body=body,
        url=review["html_url"],
        author=(review.get("user") or {}).get("login"),
        occurred_at=datetime.fromisoformat(review["submitted_at"].replace("Z", "+00:00")),
        extra={
            "repo": repo_full_name,
            "pr_number": pr_number,
            "kind": "review",
            "state": review["state"],
        },
    )


def normalize_review_comment(
    comment: dict[str, Any], repo_full_name: str, pr_number: int
) -> NormalizedItem:
    """One inline code comment on a PR — always has a body (GitHub
    doesn't allow submitting an empty one), unlike a top-level review."""
    path = comment.get("path", "")
    return NormalizedItem(
        source="github",
        source_type="review_comment",
        external_id=f"review-comment-{comment['id']}",
        title=truncate_title(f"Comment on {path}" if path else "Review comment"),
        body=comment.get("body") or "",
        url=comment["html_url"],
        author=(comment.get("user") or {}).get("login"),
        occurred_at=datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00")),
        extra={
            "repo": repo_full_name,
            "pr_number": pr_number,
            "kind": "comment",
            "path": path,
        },
    )


def normalize_commit(commit: dict[str, Any], repo_full_name: str) -> NormalizedItem:
    commit_data = commit["commit"]
    git_author = commit_data.get("author") or {}
    # `author` (linked GitHub account) may be null for commits from
    # emails GitHub can't match to a user — fall back to the raw git
    # author name in that case.
    github_user = commit.get("author") or {}

    message = commit_data.get("message", "")
    first_line = message.splitlines()[0] if message else "(no commit message)"

    return NormalizedItem(
        source="github",
        source_type="commit",
        external_id=commit["sha"],
        title=truncate_title(first_line),
        body=message,
        url=commit["html_url"],
        author=github_user.get("login") or git_author.get("name"),
        occurred_at=datetime.fromisoformat(git_author["date"].replace("Z", "+00:00")),
        extra={"repo": repo_full_name, "sha": commit["sha"][:7]},
    )

"""Orchestrates GitHub client calls + normalization into the shape
`engine/ingestion` expects. Called by `jobs/indexing.py` — nothing else
should reach into `client.py`/`normalize.py` directly."""

from collections.abc import AsyncIterator

from relay_api.connectors.github import client, normalize
from relay_api.engine.ingestion.schemas import NormalizedItem

_REPO_LIMIT = 25
"""`list_recent_repos`/`list_recent_pull_requests`/`list_recent_commits`
each pass their limit straight through as GitHub's `per_page` param in a
single request — no pagination loop, so anything up to GitHub's own
`per_page` ceiling (100) costs exactly one API call regardless of value.
`_REPO_LIMIT` is the exception: it's not free, because it's the loop
count multiplying every per-repo call below. Set with real headroom
above a live-checked account (21 repos at the time this was raised from
10), not an arbitrary round number — see the rate-limit math on
`_REVIEW_FETCH_LIMIT` below, which is where this actually costs
something."""

_PR_LIMIT_PER_REPO = 100
"""GitHub's actual `per_page` ceiling — one request either way, so this
is "capture everything a single page returns," not really a cap in the
same sense as `_REPO_LIMIT`/`_REVIEW_FETCH_LIMIT`."""

_COMMIT_LIMIT_PER_REPO = 100
"""Same reasoning as `_PR_LIMIT_PER_REPO` — GitHub's `per_page` ceiling,
free to max out."""

_REVIEW_FETCH_LIMIT = 15
"""The one limit here that's a real, per-call cost, not a `per_page`
freebie: fetching review data for every PR in every repo multiplies API
calls (2 extra requests per PR). Worst case (every repo has
`>= _REVIEW_FETCH_LIMIT` PRs): `1 + _REPO_LIMIT * (2 + 2 *
_REVIEW_FETCH_LIMIT)` calls per resync tick — at 25/15 that's ~801
calls/tick, ~3,200/hour at the 15-minute schedule (`jobs/celery_app.py`),
comfortably under GitHub's 5,000/hour authenticated ceiling with room
left for on-demand live calls (blame, browse, `engine.code_search`)
sharing the same token's budget. Real usage is well below this worst
case — not every connected repo has 15+ PRs. Same documented-cap
discipline as directory blame's `_MAX_FILES_PER_DIRECTORY` (ADR 0011).
See ADR 0016. Re-check this math (and `_REPO_LIMIT`) if the connected
account's repo count grows substantially — these aren't derived from a
formula that self-adjusts."""


async def iter_normalized_items_by_repo(access_token: str) -> AsyncIterator[list[NormalizedItem]]:
    """Same fetch/normalize work as `fetch_normalized_items`, but yields one
    connected repo's items at a time instead of accumulating every repo's
    PRs/reviews/comments/commits into one list before returning anything.

    Found live: an account with several active repos produced enough
    in-memory `NormalizedItem`s (worst case ~801 API responses' worth,
    see `_REVIEW_FETCH_LIMIT`'s own math) to OOM-kill Render's free-tier
    instance mid-sync — that whole backlog was held in memory
    simultaneously, with nothing written to the database until every repo
    had been walked. `jobs/indexing.py`'s `_iter_item_batches` persists
    (upsert + index) after each yield here, so peak memory is bounded to
    one repo's worth of items, not the connected account's."""
    repos = await client.list_recent_repos(access_token, limit=_REPO_LIMIT)

    for repo in repos:
        owner, name = repo["owner"]["login"], repo["name"]
        items: list[NormalizedItem] = []

        prs = await client.list_recent_pull_requests(
            access_token, owner, name, limit=_PR_LIMIT_PER_REPO
        )
        items.extend(normalize.normalize_pull_request(pr, repo["full_name"]) for pr in prs)

        for pr in prs[:_REVIEW_FETCH_LIMIT]:
            pr_number = pr["number"]

            reviews = await client.list_pr_reviews(access_token, owner, name, pr_number)
            for review in reviews:
                normalized_review = normalize.normalize_review(review, repo["full_name"], pr_number)
                if normalized_review is not None:
                    items.append(normalized_review)

            review_comments = await client.list_pr_review_comments(
                access_token, owner, name, pr_number
            )
            items.extend(
                normalize.normalize_review_comment(comment, repo["full_name"], pr_number)
                for comment in review_comments
            )

        commits = await client.list_recent_commits(
            access_token, owner, name, limit=_COMMIT_LIMIT_PER_REPO
        )
        items.extend(normalize.normalize_commit(commit, repo["full_name"]) for commit in commits)

        yield items


async def fetch_normalized_items(access_token: str) -> list[NormalizedItem]:
    """Full flattened list across every connected repo — kept for callers
    that genuinely want the whole account's items at once (this module's
    own tests included). `jobs/indexing.py`'s real per-connector run uses
    `iter_normalized_items_by_repo` directly instead, specifically to
    avoid materializing this whole list in memory (see that function's
    docstring)."""
    items: list[NormalizedItem] = []
    async for repo_items in iter_normalized_items_by_repo(access_token):
        items.extend(repo_items)
    return items

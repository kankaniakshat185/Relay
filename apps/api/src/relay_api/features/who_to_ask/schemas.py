from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RankingStrategy = Literal["recency", "frequency"]


class RepoOption(BaseModel):
    owner: str
    name: str
    full_name: str
    default_branch: str


class DirectoryEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]


class WhoToAskRequest(BaseModel):
    owner: str
    repo: str
    ref: str
    path: str
    strategy: RankingStrategy = "recency"
    target_type: Literal["file", "directory"] = "file"
    """`path` is a single file (existing behavior) or a directory — every
    file under it gets blamed and pooled into one set of touches before
    ranking. Set by the picker, same as `features/archaeology`."""


class CommitSummary(BaseModel):
    sha: str
    short_sha: str
    message: str
    """First line only — enough to tell what the commit actually did
    without a click-through. A bare link with no message forces the user
    to open every commit just to find out if it's relevant."""
    committed_at: datetime
    url: str


class RelatedItem(BaseModel):
    source: Literal["slack", "jira"]
    title: str
    url: str
    excerpt: str
    occurred_at: datetime


class ReviewSummary(BaseModel):
    """One piece of review commentary this person left on a PR touching
    the blamed file/directory — kept separate from `CommitSummary` (see
    `PersonScore.reviews`) so the UI never implies someone committed code
    they only reviewed."""

    pr_number: int
    pr_title: str
    excerpt: str
    url: str
    occurred_at: datetime
    state: str | None


class PersonScore(BaseModel):
    author: str
    score: float
    touch_count: int
    last_touch_at: datetime
    commits: list[CommitSummary]
    """Every commit backing this person's score, most recent first — for
    a commit-authoring contributor, `len(commits) == touch_count -
    len(reviews)`. Not capped: these are already fetched as part of
    computing the score itself, so sending all of them costs nothing
    extra; truncating for display is the frontend's job, not something to
    bake into the API. Empty for a review-only contributor — someone who
    reviewed a PR touching this file/directory but never committed to it
    themselves (ADR 0016); see `reviews` for their contribution instead."""
    reviews: list[ReviewSummary]
    """This person's review commentary on PRs associated with the blamed
    commits — a separate list from `commits`, not merged into it, so a
    reviewer is never shown as having committed code they only reviewed.
    Both feed the same `touch_count`/`score` (ADR 0016): recency/frequency
    ranking doesn't care what kind of touch it was."""
    jira_ticket_key: str | None
    jira_ticket_url: str | None
    """From the first of this person's most recent *commits* (checked up
    to 5 back) that references a Jira ticket — one lookup per person, not
    per commit (see ADR 0012 for why the cost has to be bounded this way
    once commit lists are uncapped). Always `None` for a review-only
    contributor — their reviewed PRs aren't checked for a ticket key, only
    commits are."""
    related_slack: list[RelatedItem]
    """Slack discussion related to that same ticket key — empty if none
    of the checked commits referenced one."""
    similar_issues: list[RelatedItem]
    """Other Jira issues semantically similar to `jira_ticket_key`'s own
    content — empty whenever no ticket key was found."""


class FileSearchMatch(BaseModel):
    """One candidate commit or PR the `/search` endpoint resolved — see
    `engine.code_search.service.find_files_for_query`. Picking a file
    from `files` feeds the existing `/rank` request the same way the
    repo-browse picker already does; this is just a second way to arrive
    at that same file, not a new response shape downstream."""

    kind: Literal["commit", "pull_request"]
    repo: str
    title: str
    url: str
    occurred_at: datetime
    files: list[str]
    sha: str | None
    pr_number: int | None


class WhoToAskResponse(BaseModel):
    people: list[PersonScore]
    """Highest-scored first."""
    strategy_used: RankingStrategy
    files_total: int = 1
    files_analyzed: int = 1
    files_skipped: int = 0
    """`1`/`1`/`0` in file mode — directory mode is the only case where
    these vary, but they're always present so the frontend doesn't need a
    mode branch to read them."""

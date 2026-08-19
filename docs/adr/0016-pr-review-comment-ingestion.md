# ADR 0016: PR review comment ingestion, and reviewers as first-class touches

**Status:** Accepted — Phase 2, follow-up to ADR 0012/0014/0015

## What

A new ingested source_type, `"review_comment"`, covering both a PR's
top-level review verdicts (APPROVED/CHANGES_REQUESTED/COMMENTED) and its
inline code comments. Two consumers:

- **Archaeology**: `CommitEntry.review_comments` — the PR's review
  history, plus a `PullRequestRef.has_unresolved_review` flag.
- **Who Should I Ask**: the actual functional gap this closes — reviewers
  who never committed code now appear in rankings, with their
  contribution kept visibly separate from commit authorship
  (`PersonScore.reviews`, not folded into `commits`).

## Why one source_type for two different GitHub objects

A top-level review (`GET .../pulls/{n}/reviews`) and an inline code
comment (`GET .../pulls/{n}/comments`) are different GitHub API objects,
but every downstream consumer treats them identically — both are
"commentary during code review" on a specific PR, both need the same
`extra.pr_number` join key, both render as one nested-list item. Two
source_types would mean every query and every render branch checks two
types for one concept; `extra.kind` (`"review"` vs `"comment"`) preserves
the distinction for anything that does care, without doubling the schema
surface.

## The `_REVIEW_FETCH_LIMIT` cap

Fetching review data for every PR ingestion already pulls multiplies API
calls — 2 extra requests per PR, so at `_PR_LIMIT_PER_REPO`'s full page
size, fetching review data for *every* PR in *every* connected repo
would badly outscale the 15-minute resync schedule. Capped to the
**most-recently-updated PRs per repo** instead (`_REVIEW_FETCH_LIMIT`;
see `connectors/github/ingest.py` for the current value and the live
rate-limit math behind it — checked against a real connected account,
not assumed) — `list_recent_pull_requests` already returns PRs sorted
updated-desc, so this is "review data for what's actively being worked
on," a documented, deliberate cut, not a silent truncation. Same
discipline as `_MAX_FILES_PER_DIRECTORY` (ADR 0011).

## Skipping empty-body reviews, not empty-body comments

`normalize_review` drops a review with no body — a bare "Approve" click
carries no text worth indexing or showing anyone. `normalize_review_comment`
has no equivalent check: GitHub doesn't allow submitting an inline code
comment with an empty body, so every one that exists has real content.

## `find_review_comments_for_pr`: a direct filter, in `engine/correlation`

Unlike Slack/Jira correlation (semantic search over unrelated text),
review commentary has a real FK-like relationship to its PR — so this is
a direct `extra->>'pr_number'` filter, not a search. It lives in
`engine/correlation` anyway, alongside `find_similar_jira_issues`: both
are DB-only lookups answering "what's related to this," the module's
actual job description, live-call-free either way.

## The "unresolved concerns" heuristic

`has_unresolved_concerns`: true when the most recent top-level review
*verdict* (inline comments don't count — `state is None`) is
CHANGES_REQUESTED with no later APPROVED from anyone. Documented
explicitly as a heuristic, not ground truth, same discipline as
ticket-key extraction's known false-positive rate — a real PR can be far
more nuanced (re-requested review, comments resolved out of band,
multiple reviewers with different verdicts) than "does the history, read
literally, end on a rejection."

## Reviewers as `Touch`es, and why `commits`/`reviews` stay separate

`engine.ranking.schemas.Touch`'s own docstring already anticipated this:
*"someone touched something at some time," not tied to git/blame
specifically.* Making a reviewer's commentary a `Touch` needed zero
changes to `engine/ranking` — `rank_by_recency`/`rank_by_frequency` don't
care what kind of touch it was, so a review-only contributor (never
committed, only reviewed) is ranked correctly for free.

What did need a real decision: `PersonScore.commits: list[CommitSummary]`
already implies "this person committed code." Adding reviewers into that
same list would misrepresent someone who only left review comments as
having authored commits they never touched. `PersonScore.reviews:
list[ReviewSummary]` is a separate field instead — `commits == []` for a
review-only contributor is the honest answer, not an empty state to work
around. Both lists feed the same `touch_count`/`score`.

**Cost bound**: one `find_review_comments_for_pr` call per **distinct
PR** referenced by the blamed commits, not per commit and not per person
— several commits sharing one PR (the common case) cost one lookup, same
"bound by what's actually distinct, not what's numerous" discipline as
ADR 0012's per-person Jira/Slack lookup.

**Known limitation**: a review-only contributor's `jira_ticket_key` is
always `None` — ticket-key extraction only checks a person's *commits*
(`_extract_ticket_key_from_recent_commits`), not the PRs they reviewed.
Extending that is possible but wasn't needed to close the actual gap
(reviewers being invisible to ranking at all) and was left out rather
than scope-creeping this build.

## Frontend

Archaeology's `CommitCard` gained a "Code review" section (third instance
of the same nested-list pattern used for "Related Slack discussion" and
"Similar past issues") and an "Unresolved" badge next to a PR link when
`has_unresolved_review` is true. Who Should I Ask's `PersonCard` metadata
line splits into a commit count and a review count (only shown when
non-zero), and gains a "Reviews" list alongside "Commits" — both lists
render independently, so a review-only contributor's card simply has no
"Commits" section rather than an empty one.

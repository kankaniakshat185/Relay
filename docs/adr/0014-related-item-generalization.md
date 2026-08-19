# ADR 0014: Generalizing `RelatedSlackMessage` into `RelatedItem`, and similar-past-Jira-issues

**Status:** Accepted — Phase 2, follow-up to ADR 0012

## What

Renamed `engine.correlation.RelatedSlackMessage` (and the mirrored
pydantic models in `features/archaeology/schemas.py` and
`features/who_to_ask/schemas.py`) to `RelatedItem`, adding a
`source: Literal["slack", "jira"]` field. `find_related_slack(db, user_id,
query, *, limit)` — hardcoded to `sources=["slack"]` — became
`find_related(db, user_id, query, *, sources: list[str], limit)`, a thin
wrapper over `engine.indexing.service.search` with no new retrieval logic,
just no longer hardcoded to one source.

On top of that, a new `find_similar_jira_issues(db, user_id, ticket_key,
*, limit)` gives both Archaeology's commit timeline and Who Should I
Ask's ranked people a "similar past issues" list: other Jira tickets
whose title/body are semantically close to the ticket already resolved
for that commit/person.

## Why this is the same trigger as ADR 0012, not a new exception

ADR 0005's rule — shared logic belongs in `engine/`, not duplicated — is
what created `engine/correlation/` in the first place (ADR 0012). The
same condition just fired again one level down: `RelatedSlackMessage`'s
shape (`title`, `url`, `excerpt`, `occurred_at`) was already
source-agnostic in everything but name and the `sources=["slack"]`
hardcode. Reusing it for Jira-to-Jira similarity needed one new field
(`source`, so the UI can render Slack and Jira results differently — see
below) and zero new plumbing.

## Where the ticket's own content comes from

`find_similar_jira_issues` needs the *current* ticket's title/body to use
as a search query, and getting it required no new external call.
`connectors/jira/normalize.py` already sets `url =
f"{site_url}/browse/{issue['key']}"` and `extra = {"key": issue['key'],
...}` on every ingested Jira issue, so the ticket is just a DB lookup:

```python
ticket = await db.scalar(
    select(IngestedItem).where(
        IngestedItem.user_id == user_id,
        IngestedItem.source == "jira",
        IngestedItem.extra["key"].astext == ticket_key,
    )
)
```

If the ticket was never ingested (wrong Jira site, not yet synced), the
lookup returns `None` and the function returns `[]` — not an error, just
nothing to compare against. This mirrors the existing "no ticket key
found" path both features already had.

## Self-match exclusion: filter, not a new DB feature

`find_similar_jira_issues` fetches `limit + 1` results from
`find_related(..., sources=["jira"])` and drops any result whose `url`
matches the ticket's own — the ticket is definitionally its own closest
semantic match. This was done as a post-filter in the one caller that
needs it, rather than adding an `exclude_id`/`exclude_url` parameter to
the shared `search()` function, which every other caller would have had
to ignore. Same "keep the shared primitive's signature untouched for a
single caller's need" judgment call as ADR 0012's per-person (not
per-commit) lookup scoping.

## Why `source` matters now (ties back to the original UI question)

The field was added because Slack messages, GitHub commits, and Jira
tickets had started rendering identically in Who Should I Ask despite
coming from three different systems — a real "where did this come from"
gap. `RelatedItem.source` lets the frontend label results distinctly
("Related Slack discussion" vs. "Similar past issues") instead of
presenting everything as one undifferentiated list, without needing a
second parallel type for what is structurally the same shape.

## What this does NOT do

It doesn't rank similar issues by anything other than the existing
hybrid keyword+vector search's own scoring — no separate "how similar is
similar enough" threshold was introduced. A ticket with no close matches
simply returns fewer (or zero) results, same as `find_related` already
behaved for Slack.

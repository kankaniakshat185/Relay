# ADR 0012: Shared `engine/correlation` module, and closing Who Should I Ask's Slack/Jira gap

**Status:** Accepted — Phase 2, follow-up to ADR 0010/0011

## What

Extracted Jira-ticket-key extraction, Jira URL building, and
ticket-scoped Slack search out of `features/archaeology/service.py`
(where they'd lived as private functions since Phase 2 shipped) into a
new `engine/correlation/` module. `features/who_to_ask` now uses the same
module to give each ranked person a Jira ticket link and related Slack
discussion — closing a real gap: plan.md's original spec for this
feature says experts are surfaced "via git blame/PR history **+ Slack
discussion recency**," and the Slack half was never built.

## Why this is an engine module now, not still feature-private

ADR 0005's rule is explicit: if two features need the same logic, it
belongs in `engine/`, not duplicated. That condition is now literally
true — `features/who_to_ask` needs exactly the extraction/URL/search
logic `features/archaeology` already had. `engine/correlation/` mirrors
`engine/code_context/`'s shape (`schemas.py` + `service.py`); Archaeology
was refactored onto it with zero behavior change (verified by its
existing test suite passing after only updating patch targets, not
assertions).

One fix rode along with the extraction: the old `_jira_ticket_url`
re-queried the Jira credential once per commit in Archaeology's timeline.
`engine.correlation.get_jira_site_url` is now called once per request in
both features and the resolved site URL passed to the pure
`build_jira_ticket_url` per commit/person — a real, if minor, N+1 fix,
not just a refactor.

## Why per-person, not per-commit, in Who Should I Ask

Archaeology's Slack search cost is naturally bounded — "how many distinct
commits touch one file" is small. Who Should I Ask's commit lists are
*not* bounded the same way: `PersonScore.commits` is uncapped (a prior
change — every commit is returned, truncated only for display), and
directory mode can span up to 500 files. Running one Slack search per
commit would scale with total commits across every file, not with
anything the user is actually looking at on screen.

Instead: **one Jira/Slack lookup per ranked person.** For each person,
`_extract_ticket_key_from_recent_commits` checks up to their 5 most
recent commits (not all of them) for the first extractable ticket key,
using the same commit-message → PR-title → PR-body fallback chain
Archaeology already used per commit — just applied once per person
instead. Cost now scales with the number of people shown (typically
single digits to low tens), not commits or files — the same order of
magnitude Archaeology already costs, not a multiple of it.

## What this does NOT do

It doesn't attempt to match a ranked GitHub author's identity against
Slack message authors (e.g. "did Alice from GitHub post this Slack
message"). No such cross-provider identity link exists in this app's
data model, and guessing one from display-name similarity would risk
misattributing Slack activity to the wrong person — actively harmful for
a feature whose entire point is trustworthy provenance. Instead, the
correlation is content-based: "here's Slack discussion about the same
ticket this person's recent commits reference," attributed through the
commit chain, not through matching two separate identity systems.

# Phase 2 retro: Codebase Archaeology + Who Should I Ask

**Shipped:** 2026-08-19

## What shipped

- **`engine/code_context`** (new) — live, read-only access to a user's
  GitHub repos, directory listings, and git blame. Neither feature talks
  to `connectors/github` directly; both go through this one module (ADR
  0010), the same "one engine, multiple query modes" pattern
  `engine/indexing` established for `features/context_search` in Phase 1.
  Real line-level blame, not just file-level commit history, via a new
  `connectors/github/graphql_client.py` — one GraphQL query resolves line
  ranges → commit → author → originating PR in a single round trip.
- **`engine/ranking`** (new) — two differential-tested strategies over the
  same `Touch(author, occurred_at)` data: `rank_by_recency` (exponential
  decay, configurable half-life) and `rank_by_frequency` (raw touch
  count, ties broken by recency). Neither is "correct" — they're built to
  disagree on purpose (someone who wrote most of a file two years ago and
  never touched it again vs. someone who fixed one bug yesterday), and
  `tests/differential/test_ranking_strategies.py` asserts both where they
  agree and where they diverge, per plan.md §6.
- **`features/archaeology`** — pick a repo/file (via a live GitHub file
  browser), get back a timeline of every commit currently responsible for
  a line in that file, most recent first, each with its originating PR,
  an extracted Jira ticket key (with a working ticket URL when Jira is
  connected), and related Slack messages found via Phase 1's existing
  hybrid search — reused, not reimplemented.
- **`features/who_to_ask`** — same repo/file picker, ranks everyone who's
  touched the file by recency or frequency (toggle), with sample commit
  links per person.
- **Frontend**: two new pages (`/archaeology`, `/who-to-ask`), a shared
  `RepoFilePicker` component (repo list → breadcrumb directory browser →
  file select), both built entirely from the locked `components/editorial/`
  system — no new visual patterns. Nav, footer, and the dashboard home
  page's feature grid all flipped from "Phase 2 / upcoming" to live,
  linked cards.
- **One new ADR** (0010), covering the live-vs-ingested call, why real
  GraphQL blame over simpler file history, the new engine module and its
  one documented exception to ADR 0005 (token resolution goes through
  `connectors.service` directly, matching `jobs/indexing.py`'s existing
  precedent), and the single-file scope cut below.

## What got cut or simplified within this phase

- ~~Single-file granularity only, not whole-module aggregation~~ — done,
  as a follow-up shortly after this phase shipped: see ADR 0011. Both
  features now accept a directory (via a new "Analyze this folder" action
  in the repo picker), aggregating blame across every file inside it
  (capped, concurrent, tolerant of individual file failures) and
  deduping by commit across files so a PR touching several files in the
  module still produces one timeline entry / one touch, not several.
- **No new database schema.** Blame and directory browsing are always
  live GitHub calls, never ingested — the nice consequence of the "live,
  not ingested" decision is this entire phase needed zero Alembic
  migrations. `engine/ranking` operates on data handed to it in memory,
  nothing persisted either.
- **Ticket-key extraction is a documented heuristic** (`\b[A-Z][A-Z0-9]+-\d+\b`
  against commit message, falling back to PR title/body), not a solved
  NLP problem — it has a known false-positive rate (e.g. "UTF-8" matches
  the same shape). Accepted, not silently glossed over; see ADR 0010.
- **Repo/browse endpoints exist twice** (`/v1/archaeology/repos` +
  `/v1/who-to-ask/repos`, same for `/browse`) rather than once, shared.
  This is intentional under ADR 0005 — each feature owns its own API
  surface, both calling the same `engine.code_context` underneath — not
  an oversight. Each proxy endpoint is ~5 lines.

## What was harder than expected

- **Deciding where token resolution belongs.** `engine/code_context` was
  designed to be a pure `access_token in, data out` module with no DB
  dependency — but both features need to resolve *which* access token to
  pass it, which means touching `connector_credentials`. Strictly reading
  ADR 0005 ("only engine talks to connectors") would put that resolution
  inside engine too, but that would give a deliberately stateless module a
  DB dependency it doesn't otherwise need, just to satisfy the letter of
  the rule. Resolved by treating credential/token lifecycle
  (`connectors/service.py`) as distinct from the GitHub-specific
  data-shaping logic the rule actually exists to keep out of features —
  and noting that `jobs/indexing.py` already set this exact precedent in
  Phase 1, just never written down as a rule until now (ADR 0010).
- **Collapsing blame ranges into commits, not lines.** GitHub's blame API
  returns one entry per contiguous line range, which for a file with a
  long edit history can be dozens of tiny ranges — several from the same
  commit. Naively rendering one timeline entry per range would make
  Archaeology's UI (and Who Should I Ask's touch-counting) actively
  misleading — a commit that rewrote half a file would look like it
  barely touched it, or like ten separate contributions instead of one.
  Both `features/archaeology/service.py` and `features/who_to_ask/service.py`
  collapse by commit sha before doing anything else with the data.
- **`engine/ranking`'s two strategies needed a shared, provider-agnostic
  `Touch` shape** rather than being blame-specific from the start — worth
  getting right now since a future feature reusing recency/frequency
  scoring over a different kind of "touch" (e.g. Slack message authorship
  for some future feature) shouldn't need a new ranking module.

## Addendum: what a real end-to-end run surfaced

Clicking Archaeology for real, on a genuinely connected GitHub account,
immediately produced a silent failure in the browser — no error message,
just a hung "Loading…" and a console `TypeError: Load failed`. Three
separate things were true at once, only findable by actually running it:

- **This project's GitHub OAuth App has "expire user authorization
  tokens" turned on** — an opt-in setting most OAuth Apps don't enable,
  which every docstring and ADR up to this point assumed GitHub simply
  didn't do (reasonably, for the *default* case — but this app isn't the
  default case). The stored credential's `expires_at` had already passed.
  Fixed properly, not worked around: GitHub now implements
  `refresh_access_token` exactly like Jira does (registered in
  `connectors/registry.py`'s `_REFRESHABLE_PROVIDERS`), so
  `connectors/service.ensure_valid_access_token` — already built
  generically in the token-refresh work preceding this phase — handles it
  transparently. `RefreshGrantError` (new, in `connectors/base.py`)
  normalizes GitHub's error-signaling convention (200 + an `error` body
  field) against Atlassian's (a real HTTP error status) so
  `ensure_valid_access_token` has one thing to catch regardless of provider.
- **`engine/code_context.list_repos` had zero error handling** — the only
  one of the module's three functions missing the `try/except → CodeContextError`
  pattern `list_directory` and `get_blame` already had. An expired token
  hitting GitHub's `/user/repos` raised `httpx.HTTPStatusError` completely
  unhandled, which is what actually produced the silent browser-side
  failure. Fixed, with a regression test asserting the wrap
  (`test_list_repos_wraps_http_errors_as_code_context_error`).
- **`TokenRefreshError` had no exception handler in `main.py` at all** —
  a second, worse instance of the same class of bug: even after GitHub
  refresh support existed, a refresh grant that itself failed (this
  project's actual live account: GitHub rejected the stored refresh token
  outright with `bad_refresh_token`, confirmed by hand-testing the exact
  request GitHub's docs describe — not a bug in how it was sent, just a
  token GitHub itself no longer honors) would still crash unhandled.
  Fixed with a handler mapping it to a clean 400 ("reconnect on the
  Connections page"), matching every other domain error in this app.

None of these were caught by the unit/integration test suite because
every test up to this point mocked the GitHub calls — exactly the "the
real world doesn't match the mock" pattern Phase 1's retro already named.
Reconnecting GitHub once (to get a live, honored refresh token) was the
actual unblock; every 8-hour expiry after that refreshes silently now.

## Open items carried forward

- ~~Whole-module (directory-level) aggregation~~ — done, see ADR 0011.
- Ticket-key extraction false positives — acceptable for now, would need
  real NLP or a Jira API cross-check (does this key actually exist in the
  user's connected site?) to fully close.
- Neither `engine/code_context` nor `features/archaeology`/`features/who_to_ask`
  cache blame results — every request is a live GitHub call. Fine at
  current usage; a repo with a very large/hot file could make this worth
  a short-TTL cache later.
- Why GitHub rejected this project's specific refresh token as
  `bad_refresh_token` on its very first use is still unexplained — the
  request matched GitHub's documented format exactly. Not investigated
  further since reconnecting is a one-time, low-cost recovery either way.

## Addendum: Who Should I Ask's missing Slack/Jira correlation

plan.md's spec for this feature says experts are surfaced "via git
blame/PR history + Slack discussion recency" — this phase shipped
git-only. Not a documented scope cut; a real gap, only noticed later when
asked directly whether Slack/Jira were used anywhere besides Archaeology.

Closed via ADR 0012: the ticket-key-extraction/Jira-URL/Slack-search logic
that had lived privately inside `features/archaeology/service.py` moved
into a shared `engine/correlation/` module (the ADR 0005 "two features
need it, so it belongs in engine" case, now literally true), and
`features/who_to_ask` was extended to use it — one Jira/Slack lookup per
ranked person (not per commit, since commit lists are now uncapped and
directory mode can span hundreds of files; see the ADR for the cost
reasoning). A small N+1 fix rode along: the Jira credential is now
fetched once per request in both features instead of once per
commit/person.

## Addendum: reviewers were invisible to Who Should I Ask

A second real gap in the same spirit as the one above, named directly
while comparing Relay against a broader "engineering context graph"
concept: `features/who_to_ask` only ever ranked *commit authors* — anyone
who reviewed a PR touching the file/directory, but never committed to it
themselves, never appeared in the ranking at all, even though they're
often exactly who you'd want to ask.

Closed via ADR 0016, as the third of three sequenced builds (similar past
Jira issues → ticket/PR-first entry point → this): PR review data
(top-level verdicts and inline comments) is now ingested as a new
`"review_comment"` source_type, capped to the 10 most-recently-updated
PRs per repo (`_REVIEW_FETCH_LIMIT`). `engine.ranking.schemas.Touch` — its
own docstring already anticipated this exact case — needed zero changes:
a reviewer's commentary becomes an additional `Touch`, so
`rank_by_recency`/`rank_by_frequency` rank them correctly for free.
`PersonScore` gained a `reviews` field kept separate from `commits`, so a
review-only contributor shows up honestly (`commits == []`, `reviews`
non-empty) rather than being folded into a field that implies commit
authorship. Archaeology also gained the same review data —
`CommitEntry.review_comments` plus an "unresolved concerns" heuristic
(most recent review verdict is CHANGES_REQUESTED with no later APPROVED)
— deepening its existing "why does this exist" story, not just closing
the ranking gap.

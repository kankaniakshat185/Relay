# ADR 0027: Decision Debt — ingesting decision docs, correlating them like everything else

**Status:** Accepted

## What

A new feature, **Decision Debt** (`POST /v1/decision-debt/scan`): given a
repo, flags pull requests that had real correlated Slack/Jira discussion
but no correlated decision doc — a change that clearly involved
deliberation, with no written record of why it was made the way it was.
Each flagged PR also reports whether its author has any recent commit
activity across the user's connected repos, since a flagged PR whose
author looks gone is a materially different situation than one whose
author is still around and could just be asked directly.

This required a genuinely new capability first: GitHub connectors never
ingested repo *documentation* before, only PRs/commits/reviews/messages.
Decision docs are now a fifth ingested `source_type`.

## Why

**Why ingest decision docs as `ingested_items`, not a separate table or a
live-only lookup.** The alternative — fetch decision docs live, per
request, the way `engine/code_context` fetches blame — was rejected
specifically because the whole value of this feature is *correlating*
discussion against documentation, and `engine.correlation`'s entire
pipeline (ticket-key extraction, hybrid search, the empirically-set
`_MIN_RELEVANCE_SCORE`) already operates on `ingested_items`. Standing up
a parallel live-fetch-and-compare path would mean re-deriving that whole
pipeline for one feature instead of reusing it. Ingesting decision docs
the same way everything else is ingested is also what makes them show up
in Context Search for free ("which ADR discusses X") — a real, immediate
side benefit of following the existing shape rather than a special case.

**Why a fixed folder allowlist (`docs/adr`, `docs/decisions`, `adr`,
`decisions`), not a config file.** Considered a `.prscope.yml`-style
per-repo config for teams with a different layout. Rejected for this
phase: a fixed, documented allowlist covering the two conventions
Michael Nygard's original ADR post and its common variants popularized
is the same tradeoff `_TICKET_KEY_PATTERN` already makes elsewhere in
this codebase — covers the common case honestly, doesn't try to be a
general solution. Revisit if a connected repo's real layout doesn't
match and that turns out to matter.

**Why correlation, not a new heuristic, decides "documented" vs. not.**
The original pitch for this feature considered a simpler text-matching
check ("does any doc literally mention this PR's ticket key"). Extending
`engine.correlation.find_related`/`engine.indexing.service.search` with
an optional `source_types` filter instead means decision-doc correlation
gets the exact same two-tier matching (exact ticket-key hit, falling
back to threshold-filtered hybrid search) that Slack/Jira correlation
already has — including the same false-positive protection
`_MIN_RELEVANCE_SCORE` was empirically calibrated for. A new, separate
heuristic would have needed its own calibration from scratch for a
narrower benefit.

**Why author inactivity is `False` by default, not `null`/"unknown."**
`_is_author_inactive` returns `False` whenever there isn't real evidence
of staleness — no author at all, or no commit history for them on any
connected repo. This matches this codebase's existing discipline (`ADR
0016`'s `has_unresolved_concerns`, ticket-key extraction) of a heuristic
stating plainly what it can and can't determine, rather than a
`null`/tri-state that pushes the ambiguity onto the frontend to render
somehow.

## How

- **`connectors/github/client.py`**: two new calls — `get_file_content`
  (decodes the `content` field GitHub's existing `/contents/{path}`
  endpoint returns for a file; `list_directory_contents` already hits
  this same endpoint but only for directory listings, discarding that
  field) and `get_latest_commit_for_path` (dates/attributes a doc, since
  the Contents API returns the blob, not commit history).
- **`connectors/github/normalize.py`**: `normalize_decision_doc` — title
  is the first Markdown H1 if there is one (this project's own ADRs all
  have one), else the filename.
- **`connectors/github/ingest.py`**: `_fetch_decision_docs` probes each
  of `_DECISION_DOC_FOLDERS` per repo, tolerating a 404 (folder doesn't
  exist — the expected case for most repos) the same way
  `jobs/indexing.py` already tolerates a single bad Slack channel
  without failing the whole sync. Capped at `_MAX_DECISION_DOCS_PER_FOLDER`
  (50) — real decision-doc folders are small; this guards a
  misconfigured/oversized match, not a real doc count.
- **`engine/ingestion/schemas.py`**: `SourceType` gained `"decision_doc"`.
- **`engine/indexing/service.py`**: `search` gained an optional
  `source_types` filter, independent of the existing `sources` filter —
  `sources=["github"]` alone can't distinguish a decision doc from a PR,
  both are `source="github"`.
- **`engine/correlation/service.py`**: `find_related` threads
  `source_types` through to both the semantic search and
  `_find_exact_ticket_key_matches`. `RelatedItem.source`'s type widened
  from `Literal["slack", "jira"]` to include `"github"`, since a
  correlated decision doc is a real, now-possible result shape this
  module returns.
- **`features/decision_debt`**: schemas, service (`scan`), router. The
  service is deliberately thin — it's almost entirely two `find_related`
  calls (discussion, then documentation) plus one `MAX(occurred_at)`
  query for author activity; no new retrieval logic of its own.

## Verification

Unit tests for the two new client calls, `normalize_decision_doc`
(including the filename-fallback and cross-repo external_id-collision
cases), and `_fetch_decision_docs`'s 404-tolerance/markdown-filtering/
missing-commit-history behavior. Integration tests for `search`'s and
`find_related`'s new `source_types` filter against real Postgres
(proving it narrows *within* a `sources` match, not just across
sources), and for `decision_debt.scan` itself: a real undocumented PR
gets flagged, a documented one doesn't, one below the discussion
threshold doesn't, PRs are correctly scoped to the requested repo, and
all three `author_inactive` cases (stale, recent, no history at all).
Router-level tests for the full request/response shape and the 401 for
no session. 355 tests total (350 passing — the other 5 are a pre-existing,
unrelated failure documented separately, not touched by this work), mypy
strict and ruff clean, and the route confirmed live against a running
instance, not just under tests.

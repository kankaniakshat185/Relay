# ADR 0026: Incident Correlation, and extracting `engine/timeline`

**Status:** Accepted

## What

A new feature, **Incident Correlation** (`POST /v1/incident-correlation`):
given a past timestamp and a time window, return everything ingested
across GitHub/Slack/Jira/Notes in that window — "what changed before this
broke" — optionally synthesized into a short narrative naming the most
likely candidate cause(s). A second, optional mode (v2) additionally
traces a named file's own commit history and filters it to the same
window, for "what changed in this specific file right before the
incident."

Building v2 required extracting Archaeology's commit-timeline-building
logic out of `features/archaeology/service.py` into a new
`engine/timeline/` module — this ADR covers both, since the second is
what made the first cheap.

## Why

**The retrieval half (v1) is not new capability, just a new question.**
`engine/ingestion/service.get_items_since` already existed for Weekly
Digest's "everything in the last N days" query. Incident Correlation
needs the same read, bounded on *both* sides of a point in time instead
of open-ended to now — `get_items_since` gained an optional `until`
parameter rather than a second, parallel query function existing for a
one-line difference in intent.

**The file-trace half (v2) is where the real design decision was.**
`features/archaeology/service.py`'s `trace()` already builds exactly
what v2 needs: git blame → commit → PR → Jira ticket → Slack discussion →
similar issues → review comments, for a given file. Two options:

1. Import `features.archaeology.service.trace` directly from
   `features/incident_correlation`. Rejected outright — ADR 0005's rule
   (`features/*` may only import `engine/`, never a sibling feature) has
   already fired twice for real (`engine/correlation`, `engine/synthesis`)
   specifically to prevent this exact situation.
2. Duplicate `trace()`'s body inside the new feature. Rejected — the
   logic is intricate (commit collapsing across files in directory mode,
   ticket-key extraction, unresolved-review detection) and already has
   its own test suite; a second copy is a second place for it to drift
   or be fixed only once.
3. **Extract the shared logic into `engine/`, as `engine/timeline`.**
   Chosen. Reading `trace()`'s actual body showed it was already ~90%
   calls into `engine.code_context` and `engine.correlation` — the only
   archaeology-specific part was shaping the result into
   `ArchaeologyResponse`. That's a strong sign the logic was already
   engine-shaped and just hadn't been asked to serve a second caller yet.

This is the third real instance of ADR 0005's rule firing, not a new
kind of decision — same reasoning as `engine/correlation` and
`engine/synthesis`, just for git-blame correlation instead of
ticket-correlation or LLM synthesis.

## How

- **`engine/timeline/schemas.py`**: `LineRange`, `PullRequestRef`,
  `RelatedItem`, `ReviewComment`, `TimelineEntry` (was `CommitEntry`),
  `TimelineResult` (was `ArchaeologyResponse`) — moved wholesale from
  `archaeology/schemas.py`, renamed only where the old name was
  archaeology-specific.
- **`engine/timeline/service.py`**: `build_timeline(db, user_id, *,
  access_token, owner, repo, ref, path, target_type)` — `trace()`'s full
  former body, including the `_collapse_by_commit` helper. Takes an
  already-resolved `access_token` directly, matching every other
  `engine/` module's convention (engine code never talks to
  `connectors/*` itself).
- **`features/archaeology/service.py`**: `trace()` is now four lines —
  resolve the token, call `build_timeline`, return the result.
  `archaeology/schemas.py` re-exports the moved types under their
  original names, so the wire format and every existing import are
  byte-identical — verified by Archaeology's own test suite passing
  unmodified (6 integration tests; 13 unit tests moved to
  `tests/unit/engine/test_timeline_service.py` since they test
  `build_timeline` now, not `archaeology.service`).
- **`features/incident_correlation`**: schemas (`incident_at`,
  `window_before_hours`/`window_after_hours`, optional
  `owner`/`repo`/`ref`/`file_path`), service (`correlate`, mirroring
  `weekly_digest.build_digest`'s retrieval-then-optional-synthesis
  shape), router. A `model_validator` rejects `file_path` without
  `owner`/`repo`/`ref` as a clean 422, same discipline as
  `who_to_ask`'s `pr_number` validator. A `field_validator` assumes UTC
  for a timezone-naive `incident_at` rather than raising — a browser's
  `<input type="datetime-local">` has no timezone at all, and every
  other timestamp in this app is already UTC.

## Verification

Unit tests for `get_items_since`'s new `until` bound, `engine/timeline`'s
`build_timeline` (the 13 tests moved from archaeology, unchanged in
substance), `incident_correlation`'s service (raw mode, BYOK, invalid-key
handling, the file-trace window filter) and schema validators, plus
integration tests hitting the real router (window filtering against a
real Postgres, the file-trace path against a real DB with GitHub's blame
call mocked, the 422 for `file_path` without repo fields). 325 tests
passing total (up from 314 before this ADR), mypy strict and ruff clean.

# ADR 0025: GitHub ingestion persists per repo, not all-at-once

**Status:** Accepted

## What

`connectors/github/ingest.py` gained `iter_normalized_items_by_repo`, an
async generator yielding one connected repo's `NormalizedItem`s at a time.
`jobs/indexing.py`'s `_run_indexing_for_connector` was restructured around
a new `_iter_item_batches` (replacing `_fetch_items`) that persists —
upsert, then index — after every batch, instead of once at the end of the
whole fetch. `fetch_normalized_items` (the old all-at-once entry point)
still exists, now implemented in terms of the generator, for callers that
genuinely want the full list.

## Why

Found live: a manually-triggered sync OOM-killed the Render free-tier
instance (512MB, shared with the backgrounded Celery worker and uvicorn
in the same process — `render.yaml`). The old `fetch_normalized_items`
walked every connected repo (`_REPO_LIMIT`, up to 25), and for each one
fetched its PRs, then reviews + comments for the most-recently-updated
`_REVIEW_FETCH_LIMIT` of them, then commits — accumulating every single
`NormalizedItem` from every repo into one Python list held entirely in
memory, with nothing written to the database until that whole walk
finished. ADR 0016 already worked out the worst-case call count for this
fan-out (~801 API calls/tick) as an API-rate-limit concern; the same
fan-out is also a memory concern, and nothing had bounded that side of it
— an account with several genuinely active repos (real PRs, real review
threads) was enough to reach it in practice, not just the documented
worst case.

Slack (10 channels × 50 messages) and Jira (50 issues) are small enough
in the same worst-case sense that this never surfaced there — this is a
GitHub-specific fix, not a rewrite of the shared orchestration contract.

## How

- **`iter_normalized_items_by_repo`**: identical per-repo fetch/normalize
  logic to the old `fetch_normalized_items`, restructured to `yield`
  after each repo instead of extending one outer list.
- **`_iter_item_batches`** (`jobs/indexing.py`, replacing `_fetch_items`):
  dispatches per provider same as before; for GitHub it forwards the
  generator above batch-by-batch, for Slack/Jira it yields their existing
  single-call result as one batch — no behavior change for those two.
- **`_run_indexing_for_connector`**: loops `async for batch in
  _iter_item_batches(...)`, calling `ingestion_service.upsert_items` +
  `indexing_service.index_items` after each batch rather than once at the
  end. `get_items_needing_indexing` is already scoped to `embedding IS
  NULL` (`engine/ingestion/service.py`), so calling it once per batch
  instead of once per run is safe — anything already indexed from an
  earlier batch in the same run is correctly skipped, not reprocessed.
- Total ingested/indexed counts are accumulated across batches for the
  same `index_job_completed` log line as before — this is an internal
  restructuring, not a change to what gets logged or to `last_synced_at`
  semantics.

## Consequences

- Peak memory during a GitHub sync is now bounded to one repo's worth of
  PRs/reviews/comments/commits, not the whole connected account's —
  directly fixes the OOM.
- A crash partway through a large account's sync now leaves earlier
  repos' items already ingested and indexed (each batch commits
  independently), instead of the old all-or-nothing shape where a late
  failure discarded everything gathered up to that point, same
  reasoning `_INDEX_CHUNK_SIZE` already established for the embedding
  step itself (`engine/indexing/service.py`).
- `apps/api/tests/integration/test_indexing_job.py` updated to patch the
  new `_iter_item_batches` instead of `_fetch_items` — behavior asserted
  (last-synced bookkeeping) is unchanged, only the patch point moved.

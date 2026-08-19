# ADR 0017: Manual connector sync — `last_synced_at`, a cooldown-guarded "Sync now", and "Sync all"

**Status:** Accepted — post-Phase 2

## What

The Connections page gained a real freshness signal and a way to act on
it, closing a gap found live during this session: `celery beat` (the
process that actually *triggers* the existing 15-minute periodic resync)
had silently not been running for ~24 hours, and there was no way — from
the UI, or from the data itself — to notice or fix that.

- `connector_credentials.last_synced_at`: set by
  `jobs.indexing._run_indexing_for_connector` every time a sync
  *completes*, regardless of whether it found anything new. Deliberately
  not `updated_at` (that tracks credential/token changes, e.g. a silent
  refresh, and says nothing about whether the provider's content has
  actually been re-synced).
- `POST /v1/connectors/{provider}/sync`: dispatches the same
  `index_connector_task` the periodic sweep and initial connect already
  use — no new ingestion logic, just a new trigger.
- A 60-second cooldown (`connectors.service.check_sync_allowed`),
  checked against `last_synced_at`.
- Connections page: per-provider "Sync now" + a "Sync all connected"
  button, both polling `GET /v1/connectors` until `last_synced_at` moves
  (or a timeout), rather than firing-and-forgetting.

## Why a cooldown, and why it's explicitly approximate

Each sync makes real GitHub/Slack/Jira API calls — a guard against
accidental repeated-click spam is worth having. But the cooldown is
checked against `last_synced_at`, which only updates when a sync
*completes* (a real one takes 15-40s including PR reviews), not when one
is *requested*. Several rapid clicks before the first completes could
each still dispatch a task. This catches the common case (clicking again
shortly after a completed sync), not a determined abuser — a proper
"sync in progress" flag would close that gap, but wasn't needed to fix
the actual problem (zero visibility or control over staleness at all).
Documented as a known, accepted imprecision rather than silently assumed
airtight.

## Why polling for freshness, not a webhook or push update

The frontend polls `GET /v1/connectors` every few seconds after
triggering a sync, rather than the backend pushing a completion event.
Consistent with the rest of this app's real-time story (there isn't
one — Context Search, Archaeology, Who Should I Ask are all
request/response, no websockets or SSE anywhere yet); adding push
infrastructure for one button wasn't justified. The poll has a timeout
(`SYNC_POLL_TIMEOUT_MS`) so a failed or stuck job doesn't leave the
button disabled forever.

## Why "Sync all" is three independent triggers, not one atomic operation

"Sync all connected" loops over connected providers and calls the same
per-provider `syncOne` the individual buttons use — each with its own
cooldown check, its own error, its own poll. Considered a single batched
backend endpoint instead; rejected because the three providers already
have fully independent states (one might be mid-cooldown, one might be
stale, one might not be connected) — collapsing that into one all-or-
-nothing action would either fail loudly for a provider that isn't the
user's actual concern, or require the backend to silently partial-fail
in a way the frontend can't distinguish from a real error. Three
independent triggers, one shared UI action, keeps each provider's
outcome legible.

## What this does NOT do

It doesn't distinguish "sync ran and found nothing new" from "sync ran
and updated a lot" in the UI — `last_synced_at` only says *when*, not
*what changed*. Good enough for the freshness question this was built to
answer ("is my data stale right now"); a change-summary would be a
separate, larger feature.

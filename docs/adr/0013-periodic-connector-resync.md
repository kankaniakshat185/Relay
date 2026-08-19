# ADR 0013: Periodic re-indexing via Celery Beat, one generic sweep for all three providers

**Status:** Accepted — post-Phase 2

## What

Indexing previously only ever ran once per connector: `connectors/router.py`'s
OAuth callback fires `index_connector_task.delay(...)` the moment a user
finishes connecting, and nothing re-triggers it after that. Found live —
a Slack message posted after the initial connect was invisible to search
until manually re-indexed by hand.

Fixed with a new Celery Beat schedule (`jobs/celery_app.py`) firing a new
`resync_all_connectors_task` every 15 minutes. That task is deliberately
thin: read every connected `(user, provider)` pair
(`connectors/service.list_all_credentials`, new — the one query in that
module that spans every user, not just the requesting one) and
re-`.delay()` the *existing* `index_connector_task` for each. No new
indexing logic anywhere — the fix is purely "run the thing that already
exists, again, periodically."

## Why one generic task, not provider-specific jobs

The gap is identical for GitHub, Slack, and Jira — all three only ever
indexed once. `index_connector_task` was already provider-agnostic
(`_fetch_items` dispatches internally by provider). A periodic sweep over
every credential row therefore fixes all three at once; there was never
a reason to build this three times.

## Why 15 minutes, and why polling instead of webhooks

15 minutes balances "new activity shows up in a reasonable window"
against "don't hammer three different APIs" — comfortably within all
three providers' actual rate limits even with many connected accounts
(GitHub: 5,000 req/hr; the others comparable or higher).

Webhooks (Slack Events API, GitHub webhooks, Jira webhooks) would give
near-real-time sync instead of a 15-minute worst case, but need a public
HTTPS endpoint, per-provider signature verification, and per-provider
event-shape handling — and even a webhook-based design typically still
wants periodic polling as a reconciliation backstop, since webhook
deliveries get missed in practice. Polling alone is the simpler, correct
first version; webhooks are a real future upgrade, not a gap being
glossed over.

## Operational note

This requires a `celery beat` process running *in addition to* the
existing `celery worker` — beat only schedules, it doesn't execute. Two
processes locally (see README); in production, `celery worker -B` can
combine both in a single process at small scale, but not once there's
more than one worker replica (beat would then fire duplicate schedules,
one per replica) — a real constraint to revisit before that becomes true,
not relevant yet at this project's scale.

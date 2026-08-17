# Decision 0001: Cut email as an integration

**Status:** Decided — pre-Phase 0

## What

Relay integrates with GitHub, Slack, and Jira only. Email (as a fourth
data-access connector) is explicitly out of scope, not deferred to a later
phase.

## Why

Email was on the original feature-brainstorm list as a "maybe" for the
context searcher, on the reasoning that some decisions get made in email
threads that Slack/Jira never see. Walking through the final five features
against it:

- Context Searcher — maybe, if decisions happen in email
- Codebase Archaeology — no (git → PR → Jira → Slack trail, no email step)
- Who Should I Ask — no
- Flaky Test Investigator — no (CI/git/Slack)
- Dependency Alert Bot — no (changelogs/codebase usage)

One "maybe" out of five isn't enough to justify a fourth OAuth surface,
a fourth data model to normalize into the correlation engine (ADR 0005),
and a fourth set of API quirks to handle. Every connector added without a
corresponding increase in reasoning depth is breadth-padding — exactly the
failure mode this project was explicitly trying to avoid by consolidating
around one shared engine instead of building disconnected integrations.

## How

No `connectors/email/` package exists, and none is planned. If a future
feature genuinely needs it (e.g. context search demonstrably missing
decisions that only exist in email), this decision gets revisited with a
new decision doc explaining what changed — not a silent addition.

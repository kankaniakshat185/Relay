# ADR 0005: One shared correlation engine, features query it — never each other

**Status:** Accepted — Phase 0 (enforced structurally now; the engine's
actual logic is built in Phases 1–2)

## What

`engine/` (ingestion, indexing, ranking) is the only place that talks to
connectors and builds correlated context across GitHub/Slack/Jira.
`features/*` (context_search, archaeology, who_to_ask, flaky_tests,
dependency_alerts) are query interfaces on top of it. The rule, enforced at
review time and by the package structure itself: a `features/*` module may
import from `engine/`, and never from another `features/*` module. If two
features need the same logic, that logic belongs in `engine/`.

## Why

The alternative — and the thing this project was originally scoped as —
was four-to-six separate integrations, each independently calling
GitHub/Slack/Jira APIs and doing its own correlation. That's more code, not
more capability: context search, codebase archaeology, and who-should-I-ask
all reduce to the same underlying operation — "retrieve and correlate
GitHub/Slack/Jira activity by entity and timestamp" — and differ only in
what they do with the result and how they rank it. Building that operation
four times means four sets of bugs in timestamp correlation, four rate-limit
handling implementations, four places a Slack API change breaks something.

The one-engine design also produces a much stronger architecture story than
"it connects to four things": the demo becomes "watch the same retrieval
engine answer three structurally different questions," which is a real
systems-design claim, not a feature list.

The two standalone subsystems (flaky test investigation, dependency alerts —
Phases 3–4) are deliberately **excluded** from this rule. They don't
correlate GitHub/Slack/Jira activity by entity — flaky-test detection needs
CI historical data, dependency alerts need changelog parsing and static
usage analysis. Forcing them through `engine/` just to keep one story
consistent would be the same mistake in reverse: coupling two things that
don't actually share a problem.

## Why enforce it structurally rather than just documenting it

"No feature imports another feature" is easy to say and easy to violate
under deadline pressure — someone needs one function from `archaeology/`
inside `who_to_ask/`, and the path of least resistance is a quick import.
Making the import itself the thing that gets caught in review (rather than
relying on someone remembering this ADR) is what actually holds the
boundary over four phases.

## How

- `engine/__init__.py`, `features/__init__.py` — each carries a docstring
  stating the rule (see the files themselves).
- Each `features/<name>/` module (once built, Phase 1+) owns its own
  `router.py`, `service.py`, `schemas.py` — no shared state between
  features except through `engine/`.
- Differential testing (plan.md §6) applies specifically to
  `engine/ranking/` — the one place where competing strategies (e.g.
  recency-weighted vs. frequency-weighted scoring) are meaningful to
  compare, precisely because ranking is the shared logic every feature
  depends on.
- A PR that adds an import from one `features/*` package into another is a
  request to move that logic into `engine/` instead, not to merge as-is.

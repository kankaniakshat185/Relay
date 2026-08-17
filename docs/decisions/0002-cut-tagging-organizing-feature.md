# Decision 0002: Cut the tagging/organizing-across-apps feature

**Status:** Decided — pre-Phase 0

## What

"Save/tag items from Slack, Jira, and email under unified folders/tags" —
a personal-knowledge-graph-style bookmarking feature — is not part of
Relay's scope.

## Why

Of everything considered during the initial brainstorm, this had the
weakest usefulness-to-engineering-depth ratio:

- It's fundamentally a CRUD-with-an-LLM-classifier feature — a data model
  for folders/tags plus a thin auto-categorization layer. The interesting
  part (the classifier) is a small slice of the total implementation work.
- It doesn't compose with the shared correlation engine (ADR 0005) the way
  the other five features do. Tagging is about organizing items a user
  already knows about; the engine is about correlating and surfacing items
  a user *doesn't* know are related. Building it would mean a second,
  parallel data model that doesn't reuse `engine/ingestion` or
  `engine/indexing` — a bolt-on, not a fourth query mode.
- It reads as CRUD-with-an-LLM-classifier in a demo, which undersells the
  agentic-reasoning story the rest of the project is built around.

## How

No `features/tagging/` package exists, and none is planned. This isn't a
"maybe later" — it would need a genuinely different justification than
"users might want to bookmark things" to earn a place alongside features
that all share the same retrieval/correlation backbone.

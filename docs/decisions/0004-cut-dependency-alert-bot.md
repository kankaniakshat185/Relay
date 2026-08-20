# Decision 0004: Cut Dependency Alert Bot, ship Weekly Digest instead

**Status:** Decided — post-Phase 3.5, before Phase 4 began

## What

Dependency Alert Bot — plan.md's original Phase 4 (`features/dependency_alerts`:
watch dependency version bumps, parse changelogs, cross-reference against
actual usage in the codebase via AST analysis, LLM-summarize the breaking
changes that matter) — was scoped, partially built, and then fully
reverted before shipping. `features/weekly_digest` (see ADR 0022) was
built in its place.

Scoping had already gone one round deep before the cut: npm + Python
manifest support, real static/AST analysis (not a heuristic keyword
match) via `tree-sitter` for JS/TS and Python's own `ast` module, and
LLM-based changelog summarization were all chosen over lighter
alternatives. Two model files, a GitHub client extension (`get_file_content`,
`list_releases`), and a migration existed briefly before removal.

## Why

Asked directly whether the feature sat well with Relay's overall
ideology, then asked for a recommendation against a stated goal (FAANG
SDE interview portfolio piece) rather than just an execution plan. The
honest answer: **no**, and not a close call.

- **It doesn't compose with the shared engine.** Every other feature
  (Search, Archaeology, Who Should I Ask, Notes, and now Weekly Digest)
  is a different *query mode* over the same `engine/ingestion` +
  `engine/indexing` (+ now `engine/synthesis`) backbone — that's the
  entire architectural thesis (ADR 0005). Dependency Alert Bot's actual
  data (parsed manifests, AST usage sites, changelog diffs) never touches
  `ingested_items` at all — it would have been a genuinely standalone
  subsystem living beside the engine, not a fifth thing built on top of
  it, no matter how technically deep the AST-analysis part was.
- **"More features" isn't the same as "a stronger interview story" for
  this specific goal.** A disconnected, however-impressive standalone
  subsystem dilutes a narrative that's currently unusually tight ("one
  correlation engine, several query modes, proven five different ways")
  rather than reinforcing it. An interviewer asking "walk me through the
  architecture" gets a cleaner answer with five features sharing one
  spine than with four features sharing a spine plus a fifth that
  doesn't.
- **The npm/PyPI registry calls would have been this app's first
  non-GitHub/Slack/Jira external integration** — a new category of
  external dependency (and failure mode) for a feature that, per the
  point above, wouldn't even reinforce the thing the rest of the app is
  demonstrating.

None of this is a claim that AST-based dependency analysis is
uninteresting or technically shallow — the opposite, if anything (real
`tree-sitter`/`ast` usage-site analysis is a harder problem than most of
what this app does elsewhere). The cut is specifically about fit with
*this* project's thesis and *this* stated goal, not a verdict on the idea
in general.

## How

Fully reverted before Phase 4 began — no `features/dependency_alerts`
code, models, migration, or GitHub client additions survived (the empty
`features/dependency_alerts/__init__.py` stub is the original Phase 0
scaffold placeholder, not leftover feature code). Verified via a full
test-suite re-run matching the exact pre-feature pass count, plus mypy/
ruff clean and both the dev and test databases confirmed back at the
pre-feature migration head.

Asked for new feature ideas that genuinely fit the connection/engine
idea instead of "any feature that sounds impressive" — Weekly Digest was
picked from that list specifically because it's a new *query mode*
(retrieval by time window, not keyword or file) over data the engine
already has, not a new external integration or a new standalone data
model. See ADR 0022 for what shipped instead.

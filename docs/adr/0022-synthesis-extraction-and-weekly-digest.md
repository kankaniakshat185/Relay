# ADR 0022: Extracting `engine/synthesis`, and Weekly Digest as a fifth query mode

**Status:** Accepted — post-Phase 3.5, alongside Weekly Digest

## What

Two changes that landed together, in this order:

1. **`engine/synthesis/`** (new) — `providers.py`, `schemas.py`,
   `service.py` — extracted out of `features/context_search/`, where the
   BYOK-vs-free-tier-OpenAI synthesis logic (ADR 0008) originally lived.
   `features/context_search/service.py` afterward just calls
   `engine.synthesis.service.synthesize_answer(...)` and builds its own
   `ContextSearchResponse` from the result. Zero behavior change —
   verified by the existing `test_context_search*.py`/`test_llm_providers.py`
   suites passing with only import/patch-target updates, no assertion
   changes (same bar ADR 0012 set for the `engine/correlation`
   extraction).
2. **`features/weekly_digest`** (new) — a fifth query mode over the same
   engine: instead of a keyword query (Search) or a file (Archaeology/Who
   Should I Ask), the "query" is a time window — "what happened across my
   connected GitHub/Slack/Jira/Notes in the last N days" — synthesized
   into a written digest using the exact same machinery Search's AI
   summary uses.

## Why the extraction happened first, not Weekly Digest directly reaching into `context_search`

ADR 0005 states the rule plainly: *"If a feature ever needs another
feature's logic, that's a signal the shared logic belongs in `engine/`,
not that it's fine to cross-import."* Weekly Digest needing Context
Search's BYOK-or-free-tier-OpenAI orchestration is exactly that signal,
not a hypothetical one — the alternative (Weekly Digest importing from
`features/context_search/`) would have been the second real violation of
the module-boundary rule this codebase has actually hit (the first was
ADR 0012's correlation extraction).

What moved, and what stayed:

- **Moved** (feature-agnostic): `providers.py` (the four per-provider SDK
  calls, unchanged), `SynthesisError`, `LlmProvider`/`LlmUnavailableReason`
  (moved as-is), `SourceCitation` → renamed `ItemCitation` (Pydantic field
  names unchanged, so the JSON wire shape callers depend on doesn't
  change — only the Python class name did, since "an `IngestedItem`
  presented as a citation" isn't specific to Context Search), `_to_citation`/
  `_excerpt` (pure `IngestedItem → ItemCitation` mapping), and a new
  `synthesize_answer()` that owns resolving BYOK-vs-free-tier, dispatching
  to the right provider, and normalizing `SynthesisError` into a
  `SynthesisResult`.
- **Stayed feature-side**: retrieval (`engine_search` for Context Search,
  the new `get_items_since` for Weekly Digest) and prompt-building (the
  "candidate block" + system prompt) — a question-answering prompt and a
  time-window-summarizing prompt are genuinely different per feature,
  there's nothing to share there.

## Weekly Digest's retrieval: a new mode, not a reuse of `search()`

`engine.ingestion.service.get_items_since(db, user_id, since, limit=60)`
is a plain time-window read (any source, most recent first, ordered by
`occurred_at`) — deliberately not a call into `engine.indexing.service.
search()`, which is similarity-ranked against a query string. There is no
query string here; the "query" is the time window itself. This is the
actual point of building this feature at all: it's proof "one engine,
many query modes" isn't just true for keyword-vs-file (Search vs.
Archaeology/Who Should I Ask), it also covers a genuinely different axis
— retrieval by recency instead of by relevance — over the exact same
`ingested_items` table, with zero new ingestion and no new Celery job.
Like Context Search, this is a live, on-demand read: a digest request
computes over whatever's already been ingested, the same way Search
already does.

`limit=60` is a pragmatic cap, not a claim of completeness — same
"heuristic, not ground truth" posture as `_MIN_RELEVANCE_SCORE` (ADR
0020) and the flaky-test heuristics (ADR 0018/0019): a very active
user's digest covers their most recent 60 items in the window, not
literally everything that happened. Revisit if a real account's weekly
volume regularly exceeds that and truncation becomes a visible problem,
not preemptively.

## Why the digest prompt asks for grouped cited indices, same idiom as Context Search

Weekly Digest's system prompt explicitly asks the model to group related
items (a PR, its review comments, the Slack thread about it) rather than
listing every item separately, and to return which candidate indices it
actually drew the digest from — reusing Context Search's exact
"structured JSON, not free-form prose scraped for citations" contract
(see `context_search/service.py`'s own module docstring). The same
fallback applies too: if the model cites nothing, all sources are shown
rather than none, so "the LLM didn't provide citations" never means "raw
retrieval disappears."

## What this does NOT do

No new free tier or rate-limit bucket — Weekly Digest shares Context
Search's exact `check_and_increment_daily(f"free_llm:{user.id}", ...)`
key, so both features draw from the same per-user daily OpenAI
allowance, not two independent ones. Deliberate: the free tier is a
budget on *Relay's* OpenAI bill per user, not a budget per feature.

# ADR 0020: A minimum relevance score for correlation search, plus an exact-match safety net

**Status:** Accepted — post-Phase 2, found live before Phase 3 began

## What

`engine.correlation.find_related` (used by both Archaeology's "Related
Slack discussion" and Who Should I Ask's per-person Jira/Slack links)
gained two changes to `engine.indexing.service.search`'s underlying
hybrid-scored retrieval:

- `search()` gained an optional `min_score: float | None` param —
  candidates scoring below it are excluded via `WHERE combined_score >=
  min_score`, rather than always returning however many rows `LIMIT N`
  asks for.
- `find_related` calls it with `_MIN_RELEVANCE_SCORE = 0.48`.
- `_find_exact_ticket_key_matches` — a literal `ILIKE` substring match on
  a ticket key — is unioned in ahead of the threshold-filtered results
  whenever the query is *exactly* a ticket key (`fullmatch`, not
  `search`, so this only fires for a bare key, never for free text or a
  title+body query), bypassing `_MIN_RELEVANCE_SCORE` entirely.

## Found live: a commit with zero related Slack activity was showing three unrelated messages

Looking at a real Archaeology page for a commit genuinely unrelated to
anything in Slack, "Related Slack discussion" still showed three
messages — because `search()`'s `ORDER BY score LIMIT N` unconditionally
returns up to `N` rows regardless of how weak the match is. With a small
ingested corpus (this account had exactly 4 Slack messages total at the
time), the three weakest-possible matches still filled the "related"
slot. Not a ranking bug — the ranking itself was correct — but nothing
was gating "correct-but-irrelevant" out of the response at all.

## The 0.48 threshold, derived from real scores, not guessed

`search()`'s combined score is `0.4*keyword_rank + 0.6*vector_similarity`.
Rather than pick a round number, both ends of the real gap were measured
against this account's actual ingested data:

- **Genuine matches** (an exact ticket-key hit, keyword rank contributing
  real signal): scored **0.579–0.66**.
- **Noise floor** (topically unrelated short business text, `keyword_rank
  == 0`, `vector_similarity` alone carrying the whole score): topped out
  at **0.384**.

`0.48` sits near the midpoint of that `0.384–0.579` gap, biased toward
the stricter side — cutting more borderline semantic matches rather than
risking noise back in. That bias is safe *specifically because* of the
exact-match safety net below: raising the bar can only ever discard
weaker semantic-only candidates, never a confirmed real one, since exact
matches never depend on clearing it in the first place.

## Why an exact-match safety net, added when the threshold alone turned out to be too blunt

Raising the threshold in isolation was tried first and immediately
created a new problem: a genuine ticket-key mention, but with unusually
weak vector similarity for that specific pairing of texts, could in
principle land under a stricter bar and disappear — the one case that
absolutely should never be hidden, since an exact key match is the
strongest relevance signal this app has. `_find_exact_ticket_key_matches`
resolves this by not routing that case through the blended score at all:
a direct `ILIKE` substring check on `title`/`body`, unioned ahead of the
semantic results and deduplicated by URL. It also incidentally fixes a
second gap — `search()` requires `embedding IS NOT NULL`, so a just-
ingested item that hasn't been embedded yet would otherwise be invisible
even with an exact textual match sitting right there.

`fullmatch`, not `search`, is deliberate on `_TICKET_KEY_PATTERN`: this
path only activates when the *entire* query is a bare ticket key (the
Archaeology "related Slack discussion for this commit's ticket" case) —
not when a key merely appears somewhere inside a longer free-text query
(a PR title, or `find_similar_jira_issues`'s title+body query), where an
exact-match union would be the wrong behavior — those callers want
*semantically similar*, not *the same ticket mentioned again*.

## What this does NOT do

`_MIN_RELEVANCE_SCORE` is stated explicitly as **not a universal
constant** — it was derived from one account's real data at one point in
time, the same "heuristic, not ground truth" discipline as ticket-key
extraction's own documented false-positive rate. Revisit if real usage
surfaces either false negatives (a real, non-exact match that should have
cleared the bar and didn't) or evidence it's still letting weak matches
through. No attempt to make the threshold adaptive per-user or per-corpus
size — a fixed constant, tuned once against real evidence, was enough to
fix the actual problem found live.

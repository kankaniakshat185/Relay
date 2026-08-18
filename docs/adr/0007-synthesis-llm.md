# ADR 0007: OpenAI for context-search answer synthesis

**Status:** Accepted — pre-Phase 1. Extended by
[ADR 0008](0008-raw-and-llm-search-modes-byok.md), which adds a raw
(no-LLM) mode plus BYOK support for Groq/Anthropic/Gemini — the reasoning
below for why OpenAI specifically is the *default*/free-tier provider
still holds and isn't rewritten here.

## What

`features/context_search` uses OpenAI's chat completion API (not Anthropic's
Claude API) to synthesize the source-attributed answer from retrieved
GitHub/Slack/Jira items. This is a separate call from the embedding call
(ADR 0006) — same vendor, different endpoint, different job.

## Why

This was genuinely a toss-up, and the more differentiated interview story
would have leaned Claude, given the project's Anthropic-adjacent framing.
It lost on a simpler practical basis: Relay already needs an OpenAI account
and API key for `text-embedding-3-small` (ADR 0006). Adding Anthropic on
top means a second vendor relationship, a second API key to manage across
`.env`/Render secrets, and a second billing surface — for a feature where
the *quality* of synthesis matters far more to the demo than *which*
model produced it. One vendor for both the retrieval and generation halves
of the pipeline keeps `features/context_search`'s dependency surface
smaller without giving up anything the feature actually needs.

## How

- `core/config.py` gains `openai_api_key` (shared by both the embedding
  call in `engine/indexing` and the synthesis call here).
- `features/context_search/service.py` retrieves candidate items via
  `engine/indexing`'s hybrid search, then makes one chat completion call
  with the candidates (title, snippet, source, url, author, timestamp) in
  the prompt, asking for an answer that cites which items it drew from.
  The response is parsed back into `{answer, sources: [...]}` rather than
  trusted as free-form prose, so the frontend can render real links instead
  of the model's own citation formatting.
- If this gets revisited later (e.g. swapping in Claude for a stronger
  synthesis story once the vendor-count tradeoff matters less), that's a
  new ADR, not a silent swap.

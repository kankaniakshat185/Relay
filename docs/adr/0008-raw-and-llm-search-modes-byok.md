# ADR 0008: Two search modes — raw retrieval always free, LLM synthesis opt-in and BYOK

**Status:** Accepted — post-Phase 1

## What

`features/context_search` now has two modes, both hitting the same
endpoint (`POST /v1/context-search`, `use_llm: bool` on the request):

- **Raw mode** (default): retrieval only. Returns the ranked, retrieved
  items directly — title, a short excerpt, source, and a link to the exact
  GitHub PR / Slack message / Jira issue. No LLM call, no `answer` field.
- **LLM mode** (`use_llm: true`): additionally synthesizes an answer.
  Supports four providers — OpenAI, Groq, Anthropic, Gemini — selected via
  `llm_provider`. If the request supplies its own `api_key` (BYOK), that
  key is used transiently for that one call and never stored. If it
  doesn't, the request falls back to Relay's own OpenAI key, subject to a
  small per-user daily rate limit (`free_llm_daily_limit`, Redis-backed).
  There is no free tier for Groq/Anthropic/Gemini — BYOK is required for
  those, since Relay only ever pays for its own OpenAI usage.

## Why

Two separate motivations, both real:

**Cost control.** Relay's owner doesn't want to fund unlimited LLM calls
for anyone who uses the app. Splitting retrieval (cheap, always
server-funded) from synthesis (the expensive part, gated) means the free
tier can stay genuinely free and unlimited for its actual retrieval value,
while the part that costs real money per call is either the user's own
key or a small capped allowance.

**The "is this just an AI API wrapper" question, addressed structurally,
not just argued.** Raw mode is real proof: the retrieval → correlation →
ranked-results pipeline (the actual engine, ADR 0005) works and is useful
with zero LLM involvement in the response. LLM synthesis becomes what it
should always have been — an optional layer on top of a system that
doesn't depend on it, not the thing the system *is*. Making that literal
in the API contract (a mode you can turn off and still get full value) is
a stronger answer than any amount of "well the surrounding code is
mostly not AI-related."

**BYOK across four providers**, not just OpenAI, extends the same
argument: Relay isn't wedded to one vendor's model for the one place it
does call an LLM. Groq reuses the `openai` SDK against Groq's
OpenAI-compatible endpoint — no separate client needed. Anthropic and
Gemini get their own thin adapters since their structured-output
mechanisms (forced tool-use vs. `response_schema`) are genuinely
different, but all four funnel through one `SynthesizeFn` shape so
`service.py` never branches on which provider it's talking to.

**No retry/backoff.** This is a single user-initiated call per search
(one embedding call always, one optional synthesis call), not a batch job
— there's no volume of calls for backoff to protect against, and a
transient failure is a one-click retry for the user. What *is* worth
having is turning an unhandled exception into a clean, distinguishable
reason (`invalid_api_key` vs. `provider_error` vs. `rate_limited` vs.
`api_key_required`) instead of a raw 500 — that's what `SynthesisError`
in `llm_providers.py` normalizes across all four SDKs' own exception
hierarchies.

## How

- `features/context_search/schemas.py` — `ContextSearchRequest.use_llm`,
  `.llm_provider`, `.api_key` (BYOK, never persisted).
  `ContextSearchResponse.used_llm` + `.llm_unavailable_reason` (one of
  `rate_limited` / `api_key_required` / `invalid_api_key` /
  `provider_error`) tell the frontend exactly why synthesis didn't happen,
  when it didn't. `SourceCitation.excerpt` (~200 chars, whitespace-
  collapsed) is populated in both modes.
- `features/context_search/llm_providers.py` — one `synthesize_*` function
  per provider (`openai`, `groq`, `anthropic`, `gemini`), each catching
  that SDK's own auth-error type first (→ `invalid_api_key`) and its
  general API-error type second (→ `provider_error`), raising the shared
  `SynthesisError`. `SYNTHESIS_PROVIDERS` registry maps name → function.
- `features/context_search/service.py` — orchestrates: always retrieves
  and returns sources; if `use_llm` and BYOK key present, dispatches
  straight to the chosen provider; if `use_llm` and no key, only OpenAI
  gets the free-tier path (rate-limit check via
  `core/rate_limit.check_and_increment_daily`), every other provider
  returns `api_key_required` immediately, no rate-limit check spent on a
  request that couldn't succeed anyway.
- `core/rate_limit.py` — a small Redis `INCR`/`EXPIRE` daily counter,
  scoped to exactly this one use case (not a general rate-limiting
  framework — see the module's own docstring on when to generalize it).
- `core/config.py` — `groq_synthesis_model` / `anthropic_synthesis_model`
  / `gemini_synthesis_model` defaults (used for BYOK requests that don't
  specify a model), `free_llm_daily_limit` (default 5).

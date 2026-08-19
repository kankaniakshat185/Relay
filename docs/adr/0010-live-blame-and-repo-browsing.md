# ADR 0010: Blame and repo browsing are live GitHub calls, not ingested

**Status:** Accepted — Phase 2

## What

`features/archaeology` and `features/who_to_ask` both need "which repos
does this user have," "what's in this directory," and "who last touched
this line/file" — none of which the Phase 1 connector ingests. Rather than
extending ingestion to capture file trees and blame ahead of time, both
features fetch this live, at request time, through a new engine module:
`engine/code_context/`.

- `connectors/github/client.py` gained `list_directory_contents()` (REST
  `GET /repos/{owner}/{repo}/contents/{path}`).
- `connectors/github/graphql_client.py` (new) — one function, `get_blame()`,
  hitting GitHub's GraphQL API (`https://api.github.com/graphql`) for real
  git blame: line ranges → the commit that last touched each range → its
  author → its associated pull request, all in a single query. Same OAuth
  token, same `repo` scope already granted for the REST calls — no new
  consent screen.
- `engine/code_context/service.py` — `list_repos`, `list_directory`,
  `get_blame`. Pure shaping over those two connector calls; no DB access,
  no correlation logic. Both features call this, never `connectors/github`
  directly.

## Why live, not ingested

The Phase 1 GitHub connector ingests PR metadata and commit messages only
— no file paths, no diffs, no blame (`connectors/github/client.py`, see
the Phase 1 retro). Extending ingestion to capture a full file tree plus
blame for every file in every connected repo, on every indexing run, is a
lot of data most of which would never be queried — blame is inherently
scoped to "this one file, right now," not "recent activity across a repo"
the way PRs/commits/messages are. A live call to GitHub for exactly the
file the user is asking about avoids storing data that's expensive to keep
current (blame changes with every commit) and almost always unused.

Net effect: **no new database schema, no Alembic migration** for this
entire phase's data layer — `engine/code_context` is a stateless
pass-through, and `engine/ranking` (see below) operates on data handed to
it in memory, not anything persisted.

## Why real GraphQL blame, not just file-level commit history

GitHub's REST API can answer "which commits touched this file" without
GraphQL (`GET /repos/{o}/{r}/commits?path=`), which would have been
simpler. Real line-level blame was chosen instead because it's what
plan.md §3 actually specifies ("traces why a piece of code exists: git
blame → originating PR → linked Jira ticket → related Slack discussion"),
and the GraphQL query isn't meaningfully more code — one query type,
mocked in tests the same way `httpx.AsyncClient` already is for the Jira
provider (`tests/unit/connectors/test_jira_provider.py`).

## Why a new engine module, not connectors called directly from features

ADR 0005 is explicit: only `engine/` talks to connectors; features query
engine and never each other. Both Archaeology and Who Should I Ask need
identical repo/browse/blame access — without `engine/code_context`, that
logic would either be duplicated in both features (violating the module
boundary's actual purpose) or one feature would import from the other
(violating the rule directly). `engine/code_context` is the shared
capability both build on, exactly the pattern `engine/indexing` already
established for `features/context_search`.

One narrower exception, consistent with existing precedent: both features'
`service.py` resolve the user's GitHub token via
`connectors.service.get_required_access_token()` directly, rather than
routing token resolution through `engine/code_context` too. This mirrors
`jobs/indexing.py`, which has always resolved connector credentials
itself before calling into `engine/`. Token/credential lifecycle
(`connectors/service.py`) is provider-agnostic plumbing, not the
GitHub-specific data-shaping logic ADR 0005's rule exists to keep out of
features — `engine/code_context` stays a pure `access_token in, data out`
module because of this split, rather than growing a DB dependency it
doesn't otherwise need.

## Scope cut: single file, not whole module/directory

plan.md's wording for Who Should I Ask is "given a file/module or
question" — this phase only implements the file case. Aggregating blame
across every file in a directory means one GraphQL call per file, which is
real added cost (and, for a large directory, a real latency problem) left
for a later pass if it turns out to matter. Both features' `/repos` and
`/browse` endpoints already support navigating to any directory; only the
final "rank this file" / "trace this file" step is file-scoped.

## Ticket-key extraction is a documented heuristic, not NLP

`features/archaeology/service.py` extracts a Jira ticket key via
`\b[A-Z][A-Z0-9]+-\d+\b` against the commit message, falling back to the
associated PR's title/body. This has a known false-positive rate (e.g.
"UTF-8" matches the same shape) — accepted rather than solved, the same
way other simplifications in this codebase are called out rather than
silently glossed over.

# ADR 0015: Ticket/PR-first entry point (`GET /search`), and a new `engine/code_search` module

**Status:** Accepted — Phase 2, follow-up to ADR 0010/0012/0014

## What

Archaeology and Who Should I Ask both gained a `GET {basePath}/search?q=`
endpoint — an alternative to browsing the repo tree by hand in
`RepoFilePicker`: type a ticket key, PR number, or keyword, get back
candidate commits/PRs and the files each one actually touched, pick one,
land on the exact same `trace`/`rank` request the browse flow already
produces.

## The gap this fills, and why it needs a live call

ADR 0010 deliberately scoped GitHub ingestion to commit/PR *metadata*
only — no diffs, no file paths. That was the right call for what Phase 1
needed, but it means a text search over already-ingested commits/PRs can
tell you *which* commit mentions "REL-42," not *which files* it touched —
there's nothing in the ingested row to answer that.

The fix is a live call, made only for what a search actually matched, not
during ingestion: `GET /repos/{o}/{r}/commits/{sha}` (the single-commit
endpoint, unlike the list endpoint ingestion already uses, returns a
`files` array) and `GET /repos/{o}/{r}/pulls/{n}/files`. Both are new
`engine/code_context` functions, `list_commit_files`/`list_pr_files`,
same shape and `CodeContextError` handling as the module's existing
`list_directory`/`get_blame`.

## Why a new `engine/code_search` module, not `code_context` or `correlation`

The actual coordinating function — "take a query, find matching commits/
PRs, resolve their files" — needs both a DB text search
(`engine.indexing.service.search`) and a live GitHub call
(`code_context`'s new functions). Neither existing module was a clean
home for it without breaking an invariant its own docstring states:

- `engine/code_context`'s docstring is explicit: *"Nothing here touches
  the database: every function is a live call against GitHub... there's
  nothing to ingest ahead of time."* Every function takes exactly the
  inputs its caller already has (`owner`, `repo`, `sha`, `path`) — a
  function that itself runs a DB search to *discover* those inputs is a
  different kind of thing.
- `engine/correlation`'s job is finding related *already-ingested text*
  (Slack discussion, similar Jira issues) — zero live external calls
  anywhere in it today. Bolting a live GitHub file-listing call onto it
  would quietly turn a DB-only module into one with a network dependency
  none of its other functions have, for a feature that isn't really
  "what's related," but "resolve this match to real files."

`engine/code_search/` is the new module: one function,
`find_files_for_query`, that explicitly does both steps and says so in
its own docstring, rather than smuggling a live call into a module whose
whole point was not having one. Both features import it identically —
the actual ADR 0005 trigger (two features need the same logic).

## Resolving `owner/repo/sha` from a search hit

`connectors/github/normalize.py` already sets `extra.repo` (`"owner/
name"`) on every ingested GitHub item, and `extra.number` on PRs. For
commits, the *full* SHA is `IngestedItem.external_id` — `extra.sha` is
truncated to 7 characters for display purposes and isn't guaranteed
unique enough for a live lookup, so `find_files_for_query` reads
`external_id`, not `extra.sha`.

## Failure handling: skip the bad candidate, not the whole search

`find_files_for_query` fetches up to 5 search hits and tries to resolve
each one's files live. A single candidate failing to resolve (a
force-pushed-away commit, a PR closed and later deleted) is caught and
skipped, not allowed to fail the other 4 — the same "skip it, keep going,
report what worked" discipline as directory-blame aggregation (ADR
0011's `get_blame_for_directory`).

## Frontend: a parallel path, not a replacement

`RepoFilePicker` gained a search box above the existing repo list, not in
place of it — submitting shows candidate commits/PRs with their files as
a flat clickable list. A search result already carries its own repo
(`extra.repo`), so picking a file from it looks up that repo's
`default_branch` from the picker's already-fetched `repos` list (needed
for `ref`) rather than requiring the user to browse to the repo first —
if that repo isn't in the (capped, most-recently-pushed) list, the file
buttons are simply not clickable rather than the whole picker erroring.

## What this does NOT do

It doesn't rank or score search results — `engine.indexing.service.search`
already orders by its existing hybrid keyword+vector scoring, and this
endpoint doesn't second-guess that ordering, same as `find_related`/
`find_similar_jira_issues` in ADR 0014.

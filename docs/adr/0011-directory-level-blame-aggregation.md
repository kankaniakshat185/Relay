# ADR 0011: Directory-level blame is aggregated client-request-time from N per-file blame calls, not a new API primitive

**Status:** Accepted — Phase 2, follow-up to ADR 0010

## What

Archaeology and Who Should I Ask originally only accepted a single file
(ADR 0010's scope cut). This adds a second mode, `target_type: "directory"`,
alongside the existing file mode — both features now let a user point at
a directory and get one timeline / one ranking aggregated across every
file inside it, not just one.

Since GitHub has no "blame a directory" endpoint, this is built from
primitives already in place:

- `connectors/github/client.get_tree_recursive()` — one REST call
  (`GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1`) lists every
  file in the repo at `ref`, instead of walking subdirectories one
  `list_directory_contents` call at a time.
- `engine/code_context/service.get_blame_for_directory()` — filters that
  tree to files under the requested path, then calls the existing
  `get_blame()` once per file, concurrently (`_BLAME_CONCURRENCY = 15`)
  and bounded (`_MAX_FILES_PER_DIRECTORY = 100`).
- Both features flatten every file's blame ranges and feed them through
  their **existing, unchanged** commit-collapsing logic
  (`_collapse_by_commit` / `_distinct_commits`) — dedup by commit sha
  already gives the correct behavior for a commit that touched several
  files in the directory, since that logic was never file-specific to
  begin with.

## Why aggregate at request time instead of a smarter API

GitHub doesn't expose directory-level blame, so *some* per-file
fan-out is unavoidable — the only real choice was where the cap and
concurrency bound live. Doing it in `engine/code_context` (rather than,
say, pushing multiple requests from the frontend) keeps the "engine talks
to GitHub, features never do" boundary (ADR 0005) intact, and means
`features/who_to_ask` and `features/archaeology` share one aggregation
implementation instead of two.

## The one correctness risk, and how it's handled

Naively concatenating every file's blame ranges without deduping would
inflate both outputs: a single PR touching 5 files in a directory would
produce 5 timeline entries in Archaeology (should be 1) and count as 5
touches for its author in Who Should I Ask (should be 1). Both features
already deduped by commit sha in single-file mode for an analogous reason
(one commit, many line ranges within a file); directory mode's flatten
step feeds the exact same dedup logic, just across files instead of just
within one — no new correctness logic needed, only a new place the
existing logic's generality actually gets exercised.

Archaeology additionally now tracks `files_touched: list[str]` per
timeline entry (always populated — `[path]` in file mode, the real set in
directory mode) since "which files did this commit touch in the module"
is the module-level analogue of "which lines did it touch in the file."
`line_ranges` stays empty in directory mode — flattening line numbers
across unrelated files isn't a meaningful thing to show.

## Why a cap and a concurrency bound, and why they're surfaced, not hidden

Each file costs one real GraphQL call, so uncapped means unbounded wall
clock time for a large directory — that's the actual constraint, not
GitHub's rate limits: a single blame call costs roughly 1 point against
the 5,000-points/hour GraphQL budget (no paginated connections beyond
`first: 1` on the associated-PR lookup), so even `_MAX_FILES_PER_DIRECTORY = 100`
barely registers against it, and `_BLAME_CONCURRENCY = 15` is well under
GitHub's own ~100-concurrent-request secondary-rate-limit guidance.
100 files at concurrency 15 is ~7 sequential rounds — several seconds,
not a risk of actually hitting a wall. A single file's blame failing
(binary, too large, deleted mid-request, or simply slow enough to hit its
own 15s timeout) is tolerated the same way regardless of how it fails —
skip it, keep going — via `asyncio.gather(..., return_exceptions=True)`,
which catches *any* exception a file's blame call raises, not just the
ones `get_blame` itself wraps into `CodeContextError`. Same per-item
resilience discipline as Slack's per-channel indexing failures in Phase 1.

Both the cap and any per-file failures are surfaced explicitly:
`files_total` / `files_analyzed` / `files_skipped` on both responses,
rendered in the UI as "Analyzed N of M files." Silently returning a
partial answer with no indication of that would undermine the one
property that makes either feature worth trusting — an incomplete answer
that looks complete is worse than an incomplete answer that says so.

## Who Should I Ask's commit list is uncapped server-side, truncated client-side

`PersonScore.commits` returns *every* commit backing a person's score
(`len(commits) == touch_count`), not a small sample — these are already
fetched as part of computing the score itself, so sending all of them
costs nothing extra over sending a handful. The frontend shows the first
5 with a "Show all N" expand, rather than the API deciding how much
detail is "enough": truncating on the server would mean the same
arbitrary cutoff regardless of whether the client wants to show 5, 50, or
all of them, for no actual savings. Correctness data belongs on the
response; how much of it to render at once is a display decision, not an
API one.

## What was NOT built

A live file-count preview in the "Analyze this folder" picker action
(e.g. "Analyze this folder (~22 files)") would need an extra round trip
before submitting and wasn't worth it for v1 — the counts appear in the
result itself instead. GitHub's own `truncated: true` flag (only fires on
genuinely huge repos) is treated as a hard error rather than silently
working from a partial tree, for the same "don't gloss over the limit"
reason as the file cap.

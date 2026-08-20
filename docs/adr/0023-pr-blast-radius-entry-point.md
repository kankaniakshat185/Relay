# ADR 0023: PR Blast Radius — a new Who Should I Ask entry point, not a new feature

**Status:** Accepted — post-Phase 3.6

## What

Who Should I Ask's `target_type` gained a third value, `"pull_request"`,
alongside the existing `"file"`/`"directory"` — given a specific pull
request, it ranks everyone who touched any file that PR changed, using
the exact same pooling/dedup/ranking/correlation pipeline directory mode
already had. Surfaced in `RepoFilePicker`'s existing "search a ticket,
PR, or keyword" results (ADR 0015): a PR result gains a second button,
"Rank everyone for this PR →", alongside the existing per-file buttons.

## Why this is an entry point on an existing feature, not a sixth page

Considered building this as a standalone page/feature during a "what
should Relay build next" discussion (alongside two other ideas — an
Onboarding Brief, dropped for being structurally identical to Weekly
Digest with a different filter axis, and a Drift/Stale-ticket finder,
deprioritized after live investigation showed the underlying signal was
weaker than the pitch — see the phase retro for both). PR Blast Radius
survived that scrutiny specifically because reading the real service
code (`who_to_ask/service.py`) showed directory mode already does the
hard part: pool an arbitrary *set* of files' blame ranges into one
deduped ranking. "Who touched the files this PR changed" is the same
operation; only how the file set gets resolved changes. Building it as
a sixth page would mean re-rendering the entire `PersonCard` tree
(commits/reviews/Slack/Jira sub-sections) a second time for zero new
ranking logic — the same "disconnected subsystem" smell ADR 0004
(cutting Dependency Alert Bot) already flagged, just at the page level
instead of the feature level.

## How

- **`engine/code_context/service.py`**: the concurrent per-path-blame-
  with-skip logic inlined in `get_blame_for_directory` was extracted into
  a private `_blame_paths(access_token, owner, repo, ref, paths)`, reused
  by both `get_blame_for_directory` (paths from a tree walk) and the new
  `get_blame_for_pull_request` (paths from the already-existing
  `list_pr_files`, itself built for ADR 0015's ticket/PR-first search).
  `DirectoryBlame`'s docstring was broadened rather than the type
  renamed — it was already a generic "blame these files" shape, not
  directory-specific despite the name.
- **`who_to_ask/schemas.py`**: `WhoToAskRequest.target_type` widened to
  `Literal["file", "directory", "pull_request"]`, plus `pr_number: int |
  None`. A `model_validator` rejects `pull_request` mode without a
  `pr_number` as a clean 422 — the same "reject bad input at the
  boundary" discipline as every other request schema, not a raw 500 out
  of `service.rank`'s own defensive check.
- **`who_to_ask/service.py`**: `rank()` gained a third branch calling
  `get_blame_for_pull_request` instead of `get_blame`/
  `get_blame_for_directory`. Everything downstream — dedup, ranking,
  per-person Jira/Slack correlation (ADR 0012), reviewer-as-touch ranking
  (ADR 0016) — needed zero changes, since it already only ever operated
  on "a list of `BlameRange`s," never cared which mode produced them.
- **Frontend** (`RepoFilePicker.tsx`, shared with Archaeology): the new
  button only renders when `!featureLabel` — Archaeology (which passes
  `featureLabel="Archaeology"`) never gets it, since PR Blast Radius is
  Who Should I Ask-specific. `RepoFileSelection` gained `prNumber` and a
  `displayLabel` field (a PR pools many files, so there's no single path
  to show as a results heading the way file/directory mode already can).

## Verification

Unit tests mirror the existing `test_directory_mode_*` shape in both
`test_code_context.py` (`get_blame_for_pull_request`'s pooling/skip
behavior) and `test_who_to_ask_service.py` (the `pull_request` branch's
dedup/ranking, and the model-validator rejection) — the pooling/dedup
requirements are identical to directory mode, just fed by a different
path source. One integration test ranks via `target_type: "pull_request"`
against a real ingested PR. Live-verified against a real connected
account: ranked a real PR in a real repo and confirmed the people/commits
returned matched that PR's actual changed files, not just a mocked
response.

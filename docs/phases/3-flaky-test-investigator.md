# Phase 3 retro: Flaky Test Investigator

**Shipped:** 2026-08-20

## What shipped

- **`features/flaky_tests`** (new) — Relay's fourth live feature, and the
  first one architected as a genuinely standalone subsystem rather than a
  new query mode over the shared engine: `plan.md`'s own spec calls for
  "own historical-pattern store," a deliberate exception to ADR 0005's
  "one engine, many query modes" pattern, not an oversight. Two builds:

  - **Build 1 (ADR 0018) — workflow-run-level flakiness.** A new,
    dedicated table (`flaky_test_workflow_runs`, model `WorkflowRun`),
    populated by a new Celery task (`jobs/flaky_tests.py`) polling
    GitHub Actions on the same 15-minute cadence every other connector
    already uses. `features/flaky_tests/service.py`'s `_compute_verdict`
    classifies each `(workflow, branch)` as `stable` / `flaky` / `broken`
    / `unknown` via a documented heuristic — same-commit re-runs are
    treated as the single strongest signal available, overriding the
    rate-based read entirely. New `/flaky-tests` page: repo picker →
    per-workflow verdict cards, recent-run history, linked PRs (free
    from the run's own GitHub payload — no correlation call needed).

  - **Build 2 (ADR 0019) — best-effort individual test-case detail.**
    Layered on top, never replacing Build 1: a new `CaseResult` table,
    populated by fetching and attempting to parse workflow-run artifacts
    as JUnit-shaped XML (stdlib `zipfile` + `xml.etree.ElementTree`, no
    new dependency). Returns `[]` — never raises — for anything that
    isn't a parseable report, since "this repo doesn't produce one" is
    the common, expected outcome, not a failure.

- Small, separately-scoped follow-up bundled in before Build 1 started:
  the Connections page gained real freshness visibility —
  `last_synced_at` per connector, a cooldown-guarded manual "Sync now,"
  and a "Sync all connected" action (ADR 0017) — the direct fix for a gap
  found live earlier in this session (`celery beat` had silently not been
  running for ~24 hours, with zero way to notice from the UI).

## Found live, not just in review

- **The `autodiscover_tasks` second-module gotcha, guarded against
  deliberately.** `jobs/celery_app.py`'s existing
  `autodiscover_tasks(["relay_api.jobs"], related_name="indexing")` only
  discovers a module literally named `indexing` — this is the exact
  mechanism that let `resync_all_connectors_task` go silently
  unregistered earlier in this session (see Phase 2 retro's connector
  token-refresh section for that incident's root cause). Adding
  `jobs/flaky_tests.py` needed its own `autodiscover_tasks(...,
  related_name="flaky_tests")` call — verified live this time, not
  assumed: a fresh `celery worker` was started and its startup `[tasks]`
  listing checked for both module's tasks before either build was called
  done.
- **`pull_requests[].url` on a GitHub Actions run object is an API
  endpoint, not a browsable page.** Caught during implementation, before
  it shipped, by actually reading GitHub's response shape rather than
  assuming every URL-shaped field points at a web page. The real link is
  constructed from parts already in hand (`repo`, `pr.number`).
- **A real UI redundancy, caught from a live screenshot, not a design
  review.** The first version of the workflow card showed the latest run
  twice — once as a standalone "Latest run" line, once again as the
  first entry in "Recent runs" below it. Fixed by folding PR links into
  each run-history entry instead of a separate headline line, which also
  ended up more informative (shows which specific run in the history a
  PR maps to, not just the most recent one).
- **A real, if minor, code-quality catch.** The `TestCaseResult` model
  class name collided with pytest's default `Test*` class-discovery
  convention — any test file that imported it by name triggered a
  `PytestCollectionWarning` on every run. Renamed to `CaseResult` rather
  than silenced, since the warning was correct: naming non-test code with
  a `Test` prefix is a known footgun.
- **Build 2's "best-effort" design proved itself on the very first live
  run**, not just in the abstract: a real sync against a connected
  account hit 20+ real artifacts across several repos, every one of them
  a coverage report (`coverage-html.zip`), none of them JUnit — and every
  single one was correctly downloaded, recognized as unparseable, and
  skipped, with zero errors and zero incorrectly ingested rows.
- **The rerun-as-flaky signal was over-broad — caught by reading the
  user's own live screenshots, not review.** The original heuristic
  treated *any* `run_attempt > 1` as override-strength flaky evidence,
  even when that re-run's own current outcome was still `failure`. Since
  `WorkflowRun` upserts to GitHub's latest attempt only (no per-attempt
  history retained), "retried and still failing" is genuinely
  indistinguishable from "retried and it flipped" using that data alone —
  so only a re-run whose current conclusion is `success` is treated as
  unambiguous now; a still-failing re-run falls through to the normal
  streak logic instead. Landed alongside a cross-check against Build 2's
  per-test data (`has_test_case_data`), so a rerun-driven `flaky` verdict
  with no corroborating flaky test now says so on the page, rather than
  implying the rerun alone proves a specific test is non-deterministic.
  See ADR 0018's updated verdict section for the full before/after.
- **Layered ground truth on top of that same fix, same session.** The
  "successful re-run" rule above is itself still an assumption (infers
  attempt 1 must have failed from the current outcome). Added a
  best-effort per-attempt fetch (`WorkflowRun.first_attempt_conclusion`,
  capped at 20 re-runs per repo per sync) that gets GitHub's own record of
  what attempt 1 actually concluded, so a real flip in either direction —
  not just "ended in success" — can be detected when available, falling
  back to the assumption only when it isn't. A live sync against the same
  connected account hit all three shapes in one pass: a genuine non-flip
  (`failure -> failure`, correctly excluded — this run alone would have
  forced `flaky` under the original rule), two genuine flips (`failure ->
  success`, correctly counted), and one attempt-1 outcome that wasn't
  directly comparable (`cancelled`, correctly fell back to the
  assumption). See ADR 0018's "Layering in ground-truth re-run detection"
  section.

## Open items carried forward

- **No test currently in this account's connected repos produces a
  JUnit-shaped artifact**, so Build 2's actual parse-and-ingest path
  (as opposed to its graceful-skip path) has only been proven against
  synthetic fixtures in tests, not a real repo's real output. Worth a
  follow-up live check once a connected repo's CI actually uploads one.
- **Per-test identity is `(classname, test_name)` only** — a renamed
  test starts a fresh flakiness history under its new name, with no way
  to carry the old history forward. Same class of limitation as any
  name-based tracking elsewhere in this app (e.g. ticket-key extraction).
- **No cross-provider CI support.** GitHub Actions only — GitLab CI,
  CircleCI, Jenkins, etc. are out of scope, consistent with this app's
  GitHub-first connector story so far.
- **The flakiness heuristics (both levels) are unvalidated against a
  large, realistic run history** — same honest caveat as Who Should I
  Ask's ranking strategies and Archaeology's ticket-key extraction:
  reasonable, documented starting points, not tuned against real-world
  data at scale.

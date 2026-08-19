# ADR 0018: Flaky Test Investigator — workflow-run-level flakiness, a standalone store, polling ingestion

**Status:** Accepted — Phase 3, Build 1 of 2 (workflow-run level; individual
test-case detail is Build 2, ADR 0019)

## What

Relay's third live-ish feature (`plan.md` §3.4): "correlates CI failures
against historical flakiness patterns and recent related PRs." Build 1
ships the reliable half — per-workflow flakiness verdicts computed from
GitHub Actions run history, polled on the same 15-minute cadence as every
other connector.

- `features/flaky_tests/models.py`: `WorkflowRun`, a new, standalone
  table (`flaky_test_workflow_runs`) — **not** `ingested_items`.
- `jobs/flaky_tests.py`: a separate Celery task polling
  `list_workflow_runs` per connected user's repos, upserting into that
  table.
- `features/flaky_tests/service.py`: `analyze_workflows` groups ingested
  runs by `(workflow_name, head_branch)` and computes a verdict via a
  documented heuristic.
- New `/flaky-tests` page: pick a repo, see each workflow's verdict,
  recent-run summary, and associated PRs (already on the run's own
  GitHub payload — no correlation call needed).

## Why a standalone table, not `ingested_items`

`plan.md` scopes this feature as a standalone subsystem specifically so
it "integrates cleanly without polluting the core engine" — a real
architectural exception to ADR 0005's "one engine, many query modes," not
an oversight. Workflow runs don't fit `ingested_items`' shape or its
consumers' assumptions (no embedding/search_vector need — nobody
semantically searches CI runs; a run's `conclusion`/`status` mutate over
its lifetime in a way `IngestedItem`'s "immutable-ish content" upsert
model isn't built for — see the re-run/in-progress→completed transition
test). A dedicated table with its own upsert semantics fits the actual
data better than forcing a shared shape to accommodate it.

## Why polling, not webhooks

Reuses the same 15-minute Celery Beat pattern every other connector
already uses — no new infrastructure. A webhook receiver would need a
public endpoint, signature verification, and per-repo registration this
app doesn't have; for a feature about historical *patterns*, not "the
instant this run finished," the 15-minute lag costs nothing real.

## The `autodiscover_tasks` gotcha — found once already, guarded against here

`jobs/celery_app.py`'s `autodiscover_tasks(["relay_api.jobs"], related_name="indexing")`
only discovers a module literally named `indexing`. A second task module
(`jobs/flaky_tests.py`) needed its own `autodiscover_tasks(..., related_name="flaky_tests")`
call — Celery supports multiple `on_after_finalize` hooks, so the two
calls don't clobber each other, but this was **verified live**, not
assumed: a fresh `celery worker` was started and its startup `[tasks]`
listing checked for both `jobs.indexing.*` and `jobs.flaky_tests.*`
entries before this was called done. Worth the extra step — this exact
class of bug (a task silently never registering, because the process
running it predates the code that would register it, or because
discovery never found it in the first place) already cost real debugging
time earlier this session, on the `resync_all_connectors_task` itself.

## The verdict heuristic, and its real limits

`_compute_verdict` (see its own docstring for the full definition):
`unknown` (nothing completed yet) → `stable` (no failures, no *recovered*
re-runs) → `broken` (failed and stayed failed — no pass after the first
failure) → `flaky` (a pass after an earlier failure, or any same-commit
re-run that *succeeded*, treated as the strongest possible signal and
overriding the rate-based read entirely).

A **heuristic**, not ground truth, same discipline as ticket-key
extraction's documented false-positive rate: it can't distinguish "flaky
because of a race condition in the test itself" from "flaky because
something *outside* the pinned commit changed between attempts" — an
unpinned dependency version, a `latest`-tagged Docker image, a
third-party GitHub Action referenced by a mutable ref (`@main`) instead of
a pinned SHA/tag. Same-commit re-runs guarantee the *repo's own code* is
identical across attempts — GitHub's re-run mechanism always re-checks-out
the same pinned `head_sha`; there's no way to fix the source and then
"re-run" the old attempt, that always creates a brand-new run (`run_id`,
`run_attempt = 1`) on the new commit instead, which this system tracks as
ordinary pass/fail history, never as rerun evidence. What the guarantee
does *not* cover is everything the workflow pulls in from outside that
commit — so "flaky" here means "this workflow's outcome isn't
reproducible for a given commit," a broader claim than "this test has a
race condition," and deliberately so: an unpinned dependency making CI
unreliable is exactly the kind of thing worth surfacing, even though the
fix (pin the dependency) differs from fixing a racy test. A young workflow
(few runs ingested yet) can also look artificially stable or broken until
more history accumulates. Computed fresh on every request from the
current window (`engine/ranking`'s "compute on demand, don't persist a
decision" discipline) — a verdict isn't stored, so it can't go stale
independent of the underlying data.

**Only a *successful* re-run overrides the verdict — found live, fixed
after shipping.** The original version treated any `run_attempt > 1`
as override-strength flaky evidence, full stop. Looking at real data from
a connected account surfaced the gap: `WorkflowRun` stores one row per
`run_id`, upserted to GitHub's latest attempt — a re-run's earlier
attempt is never retained, so a run currently showing `run_attempt > 1`
and `conclusion == "failure"` is genuinely ambiguous from this data alone
("retried and it flipped to fail" vs. "genuinely broken, retried out of
hope, failed again"). Only a re-run whose *current* conclusion is
`success` is unambiguous evidence — same commit, a later attempt reached
a different, better result. `rerun_count` (surfaced to the user as "N
same-commit re-runs detected") still counts every re-run regardless of
outcome; only which re-runs are allowed to force the verdict changed.
Cross-checked against Build 2 at the same time: `WorkflowVerdict.
has_test_case_data` now distinguishes "no test-case data was ever
captured" (the common case) from "test-case data exists and genuinely no
individual test looks flaky" — the latter is a real signal that a
rerun-driven `flaky` verdict may reflect infra/setup flakiness rather than
a non-deterministic test, and the `/flaky-tests` page says so explicitly
when it applies.

## Layering in ground-truth re-run detection

The "successful re-run" rule above is still an *assumption*, not a
measurement — it infers "attempt 1 must have failed" from "a re-run
happened and now reads `success`," on the theory that people
overwhelmingly re-run failing workflows, not passing ones. That inference
can't see a genuine `success -> failure` flip at all, and can't be sure a
still-`failure` re-run isn't secretly a flip either.

`WorkflowRun.first_attempt_conclusion` closes that gap where it's cheap
to: for any re-run, `jobs/flaky_tests.py` makes one best-effort call to
GitHub's per-attempt endpoint (`GET .../runs/{run_id}/attempts/1`,
`connectors/github/client.py`'s `get_workflow_run_attempt`) to fetch what
attempt 1 *actually* concluded, capped by `_ATTEMPT_FETCH_LIMIT` (20 per
repo per sync — re-runs are rare, so this is generous) and never re-fetched
once captured (attempt 1's outcome is immutable, same reasoning as
`CaseResult`). `service._rerun_is_flaky_evidence` prefers this ground
truth when present — a real flip in *either* direction counts, not just
"ended in success" — and falls back to the original assumption-based rule
only when the fetch was never made or the attempt's own conclusion isn't
directly comparable (e.g. `cancelled`).

**Live-verified against the exact account this ADR's original section
was written from, and it exercised every case in one sync:**
- `bcea1fe` (main, attempt 2): ground truth showed `failure -> failure` —
  a genuine non-flip. Correctly excluded from evidence now; under the
  original rule this run alone would have forced `flaky`.
- `b37a13b` (main, attempt 3) and `fcd9242` (dev, attempt 2): ground
  truth confirmed real `failure -> success` flips — correctly counted.
- `efa277d` (dev, attempt 2): attempt 1 was `cancelled`, not directly
  comparable to a completed conclusion — correctly fell back to the
  assumption-based rule (`success` now → counted).

Both `strata` workflows still read `flaky` after this change, but for a
provably correct reason now (`b37a13b`/`fcd9242`'s real flips) rather than
`bcea1fe`'s non-flip incorrectly carrying the verdict.

## `pull_requests[].url` is constructed, not trusted from the payload

Found during implementation, before it shipped: GitHub's workflow-run
`pull_requests` array carries a minimal PR reference whose `url` field is
the REST API endpoint (`api.github.com/repos/.../pulls/N`), not a
browsable page — there's no `html_url` in that object at all. The real
web link (`github.com/{repo}/pull/{number}`) is built from parts already
in hand (`repo`, `pr.number`) in `jobs/flaky_tests.py`'s `_parse_run`,
not read from the payload. Caught by re-reading GitHub's actual response
shape rather than assuming every URL-shaped field in a GitHub API payload
points at a web page.

## Live verification performed

Migration applied to a real database; a fresh `celery worker` confirmed
registering all four tasks (two from `indexing`, two from `flaky_tests`);
`sync_flaky_tests_task` triggered manually against a real connected
GitHub account (21 repos, ~19.5s, zero errors); ingested rows inspected
directly; `analyze_workflows` run against that real data producing
sensible verdicts (a repo with a same-commit re-run correctly reading
`flaky`, a clean-passing repo reading `stable`); live HTTP smoke check on
both new routes.

## What Build 1 does NOT do

No individual-test-case detail — a workflow with genuinely flaky
*specific tests* buried inside an otherwise-passing run looks `stable`
here, since the verdict only sees the workflow's own pass/fail
conclusion. That's Build 2 (ADR 0019): best-effort JUnit-artifact
parsing layered on top, degrading gracefully when unavailable, not a
replacement for this workflow-level view.

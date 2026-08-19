"""Analyzes ingested GitHub Actions workflow-run history
(`features.flaky_tests.models.WorkflowRun`, populated by `jobs.flaky_tests`)
into a per-workflow flakiness verdict. Also surfaces individual flaky
test cases where that data was captured (`CaseResult`, best-effort,
ADR 0019). Read-only over both tables — `list_repos` below is the one
exception, reusing `engine.code_context` the same way Archaeology/Who
Should I Ask do for their own repo pickers (ADR 0005: shared feature
logic belongs in engine).

Deliberately still just a heuristic, not ground truth — see
`_compute_verdict`'s and `_compute_test_case_verdict`'s own docstrings
for their exact definitions and limits, same discipline as ticket-key
extraction and the unresolved-review flag elsewhere in this app. See ADR
0018 (workflow-level) and ADR 0019 (test-case level).
"""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.engine.code_context import service as code_context_service
from relay_api.features.flaky_tests.models import CaseResult, WorkflowRun
from relay_api.features.flaky_tests.schemas import (
    PullRequestRef,
    RepoOption,
    RunSummary,
    TestCaseVerdict,
    Verdict,
    WorkflowVerdict,
)

_RECENT_RUNS_SHOWN = 10
"""How many of a workflow's most recent runs to include in the response
for display — separate from how many were *ingested*
(`jobs.flaky_tests`'s `_RUN_FETCH_LIMIT`) or how many feed the verdict
(all ingested ones, see `_compute_verdict`); this only bounds what the UI
renders per workflow."""

_MAX_FLAKY_TEST_CASES_SHOWN = 20
"""Caps `WorkflowVerdict.flaky_test_cases` (ADR 0019) — a genuinely
unstable test suite could have many flagged tests; this bounds response
size the same way `_RECENT_RUNS_SHOWN` does for runs, not a claim that a
21st flaky test doesn't matter."""

_VERDICT_ORDER: dict[Verdict, int] = {"broken": 0, "flaky": 1, "unknown": 2, "stable": 3}
"""Highest-signal-first ordering for the response — a user opening this
page almost certainly wants to see what's broken or flaky before a wall
of stable workflows."""


async def list_repos(db: AsyncSession, user: User) -> list[RepoOption]:
    token = await connector_service.get_required_access_token(db, user.id, "github")
    repos = await code_context_service.list_repos(token)
    return [RepoOption(**vars(r)) for r in repos]


def _rerun_is_flaky_evidence(run: WorkflowRun) -> bool:
    """Whether one same-commit re-run (`run.run_attempt > 1`) counts as
    override-strength flakiness evidence. Two layers, ground truth
    preferred over the assumption-based fallback:

    - **Ground truth** (`run.first_attempt_conclusion` set — a
      best-effort per-attempt fetch, `jobs.flaky_tests`, capped by
      `_ATTEMPT_FETCH_LIMIT`): a genuine flip between what attempt 1
      actually concluded and what this run currently shows, in *either*
      direction. `success -> failure` is just as real evidence as
      `failure -> success` — the code didn't change and the result did.
    - **Fallback** (`first_attempt_conclusion` is `None` — not every
      re-run gets fetched): `WorkflowRun` only ever stores the *latest*
      attempt's own conclusion, so without the ground-truth fetch we
      can't see what attempt 1 actually returned. A re-run currently
      reading `success` is treated as evidence under the assumption that
      re-runs are triggered in response to a failure, not a pass (nobody
      manually re-runs a workflow that already passed) — so a still-
      `failure` re-run isn't treated as evidence either way; it's equally
      consistent with "flipped from success" (rare, and this can't tell)
      and "genuinely broken, retried out of hope, failed again" (the
      far more common case)."""
    if run.first_attempt_conclusion in ("success", "failure"):
        return run.first_attempt_conclusion != run.conclusion
    return run.conclusion == "success"


def _compute_verdict(runs: list[WorkflowRun]) -> tuple[Verdict, int, int, int, int]:
    """`runs` sorted oldest-first, one `(workflow_name, head_branch)`
    group. Returns `(verdict, total_considered, passed, failed, rerun_count)`.

    A **heuristic**, not ground truth — same discipline as ticket-key
    extraction's documented false-positive rate:
      - `unknown`: nothing completed yet (all queued/in-progress, or no
        runs ingested).
      - `stable`: no failures among completed runs, and no re-run counts
        as flaky evidence (see `_rerun_is_flaky_evidence`).
      - `broken`: has failed, and once the first failure happened nothing
        passed again afterward — a clean "started failing, stayed
        failed" streak, reads as a real regression rather than noise. A
        re-run with no flaky evidence behind it does not change this read.
      - `flaky`: everything else — a pass occurred *after* an earlier
        failure (the outcome isn't monotonic), or a same-commit re-run
        counts as flaky evidence (the single strongest signal available
        when it applies: the code didn't change and the result did).

    `rerun_count` (returned below, shown to the user as "N same-commit
    re-runs detected") counts *every* re-run regardless of whether it
    counts as evidence — only which re-runs are allowed to force the
    verdict is filtered by `_rerun_is_flaky_evidence`.

    Real limits, stated plainly: this can't distinguish "flaky because of
    a race condition" from "flaky because of a genuinely intermittent
    external dependency," and a young workflow (few runs yet) can look
    artificially stable or broken until more history accumulates. Not
    revisited from historical data once verdicts are shown — every
    request recomputes from the current window, same "compute on demand,
    don't persist a decision" discipline as `engine/ranking`.
    """
    completed = [r for r in runs if r.conclusion in ("success", "failure")]
    total = len(completed)
    passed = sum(1 for r in completed if r.conclusion == "success")
    failed = total - passed
    rerun_count = sum(1 for r in runs if r.run_attempt > 1)
    flaky_rerun_count = sum(1 for r in runs if r.run_attempt > 1 and _rerun_is_flaky_evidence(r))

    if total == 0:
        return "unknown", total, passed, failed, rerun_count
    if failed == 0:
        verdict: Verdict = "flaky" if flaky_rerun_count > 0 else "stable"
        return verdict, total, passed, failed, rerun_count
    if flaky_rerun_count > 0:
        return "flaky", total, passed, failed, rerun_count

    first_failure_idx = next(i for i, r in enumerate(completed) if r.conclusion == "failure")
    any_pass_after = any(r.conclusion == "success" for r in completed[first_failure_idx + 1 :])
    verdict = "flaky" if any_pass_after else "broken"
    return verdict, total, passed, failed, rerun_count


def _compute_test_case_verdict(outcomes_chronological: list[str]) -> tuple[Verdict, int, int, int]:
    """Build 2 (ADR 0019) — same shape of question as `_compute_verdict`,
    applied per individual test instead of per workflow run. Simpler:
    there's no rerun signal at this granularity (a re-run is tracked per
    *run*, not per individual test within it — every test in a rerun run
    would show the "same commit, different result" signal identically,
    so it wouldn't discriminate between tests the way it does between
    workflows). `outcomes_chronological` is `"passed" | "failed" |
    "skipped"`, oldest first, for one `(classname, test_name)` pair."""
    considered = [o for o in outcomes_chronological if o in ("passed", "failed")]
    total = len(considered)
    passed = sum(1 for o in considered if o == "passed")
    failed = total - passed

    if total == 0:
        return "unknown", total, passed, failed
    if failed == 0:
        return "stable", total, passed, failed

    first_failure_idx = considered.index("failed")
    any_pass_after = "passed" in considered[first_failure_idx + 1 :]
    verdict: Verdict = "flaky" if any_pass_after else "broken"
    return verdict, total, passed, failed


async def _analyze_test_cases(
    db: AsyncSession, run_ids: list[uuid.UUID]
) -> tuple[list[TestCaseVerdict], bool]:
    """Only ever called with the run ids of one `(workflow_name,
    head_branch)` group — returns the individual tests whose own history
    looks flaky or broken (`stable`/`unknown` ones are dropped; with
    potentially hundreds of tests per suite, showing only the ones worth
    looking at is the point), plus whether *any* test-case data was
    captured for this group at all. That second value is what lets
    `analyze_workflows` tell "no JUnit-shaped artifact was ever captured
    for this workflow" (silent, expected — ADR 0019) apart from "test-case
    data exists and genuinely none of it looks flaky" (a real, useful
    signal when the workflow's own verdict is `flaky` on a rerun alone —
    see `WorkflowVerdict.has_test_case_data`)."""
    if not run_ids:
        return [], False

    result = await db.execute(
        select(CaseResult, WorkflowRun.run_started_at)
        .join(WorkflowRun, CaseResult.workflow_run_id == WorkflowRun.id)
        .where(CaseResult.workflow_run_id.in_(run_ids))
        .order_by(WorkflowRun.run_started_at.asc())
    )
    rows = result.all()
    if not rows:
        return [], False

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for test_case, _started_at in rows:
        grouped[(test_case.classname, test_case.test_name)].append(test_case.outcome)

    verdicts = []
    for (classname, test_name), outcomes in grouped.items():
        verdict, total, passed, failed = _compute_test_case_verdict(outcomes)
        if verdict in ("flaky", "broken"):
            verdicts.append(
                TestCaseVerdict(
                    classname=classname,
                    test_name=test_name,
                    verdict=verdict,
                    total_considered=total,
                    passed_count=passed,
                    failed_count=failed,
                )
            )

    verdicts.sort(key=lambda v: (_VERDICT_ORDER[v.verdict], v.classname, v.test_name))
    return verdicts[:_MAX_FLAKY_TEST_CASES_SHOWN], True


def _to_run_summary(run: WorkflowRun) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        conclusion=run.conclusion,
        status=run.status,
        run_attempt=run.run_attempt,
        head_sha=run.head_sha,
        html_url=run.html_url,
        run_started_at=run.run_started_at,
        pull_requests=[PullRequestRef(**pr) for pr in run.pull_requests],
    )


async def analyze_workflows(db: AsyncSession, user: User, repo: str) -> list[WorkflowVerdict]:
    """`repo` is `"owner/name"` — matches how it's stored on `WorkflowRun`."""
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.user_id == user.id, WorkflowRun.repo == repo)
        .order_by(WorkflowRun.run_started_at.asc())
    )
    runs = list(result.scalars().all())

    grouped: dict[tuple[str, str], list[WorkflowRun]] = defaultdict(list)
    for run in runs:
        grouped[(run.workflow_name, run.head_branch)].append(run)

    workflows = []
    for (workflow_name, head_branch), group in grouped.items():
        verdict, total, passed, failed, rerun_count = _compute_verdict(group)
        recent = sorted(group, key=lambda r: r.run_started_at, reverse=True)[:_RECENT_RUNS_SHOWN]
        flaky_test_cases, has_test_case_data = await _analyze_test_cases(db, [r.id for r in group])
        workflows.append(
            WorkflowVerdict(
                workflow_name=workflow_name,
                head_branch=head_branch,
                verdict=verdict,
                total_considered=total,
                passed_count=passed,
                failed_count=failed,
                rerun_count=rerun_count,
                recent_runs=[_to_run_summary(r) for r in recent],
                flaky_test_cases=flaky_test_cases,
                has_test_case_data=has_test_case_data,
            )
        )

    workflows.sort(key=lambda w: (_VERDICT_ORDER[w.verdict], w.workflow_name))
    return workflows

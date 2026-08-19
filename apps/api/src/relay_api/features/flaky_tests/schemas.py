from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Verdict = Literal["stable", "flaky", "broken", "unknown"]


class RepoOption(BaseModel):
    owner: str
    name: str
    full_name: str
    default_branch: str


class PullRequestRef(BaseModel):
    number: int
    url: str
    """A real, browsable `github.com/.../pull/N` link — built from the
    repo + PR number in `jobs.flaky_tests._parse_run`, not taken directly
    from GitHub's run payload (whose `pull_requests[].url` is an API
    endpoint, not a web page)."""


class RunSummary(BaseModel):
    run_id: int
    conclusion: str | None
    status: str
    run_attempt: int
    head_sha: str
    html_url: str
    run_started_at: datetime
    pull_requests: list[PullRequestRef]
    """plan.md's "recent related PRs" — comes straight from GitHub's own
    run payload, no correlation lookup needed."""


class TestCaseVerdict(BaseModel):
    """Build 2 (ADR 0019) — one individual test whose own history looks
    flaky or broken. Only ever populated from runs where a JUnit-shaped
    test-report artifact was found and parsed; a workflow with no
    captured test-case data simply has an empty
    `WorkflowVerdict.flaky_test_cases`, not an error."""

    classname: str
    test_name: str
    verdict: Verdict
    total_considered: int
    passed_count: int
    failed_count: int


class WorkflowVerdict(BaseModel):
    workflow_name: str
    head_branch: str
    verdict: Verdict
    total_considered: int
    """Completed (success/failure) runs the verdict was computed from —
    excludes in-progress/queued/cancelled/skipped runs."""
    passed_count: int
    failed_count: int
    rerun_count: int
    """How many considered runs were a re-run of a previous attempt on
    the same commit — a direct, same-code signal of non-determinism, not
    folded silently into the pass/fail rate."""
    recent_runs: list[RunSummary]
    """Most recent first, capped for display — not the full ingested
    history a verdict was computed from."""
    flaky_test_cases: list[TestCaseVerdict]
    """Individual tests whose own history looks flaky or broken —
    best-effort (ADR 0019), empty whenever no test-case data was
    captured for this workflow's runs. A workflow-level verdict of
    `stable` can still list flaky test cases here if per-test outcomes
    happened to cancel out at the workflow level; the two aren't required
    to agree, and neither is "more correct" than the other — they're
    answering different questions."""
    has_test_case_data: bool = False
    """Whether *any* JUnit-shaped test-case data was captured for this
    workflow's runs, regardless of whether any of it looks flaky. Lets a
    `flaky` verdict with an empty `flaky_test_cases` be read correctly:
    `False` means "never captured, can't confirm either way" (the common,
    expected case — ADR 0019); `True` means test-case data exists and
    genuinely none of it points at a specific flaky test, which is a real
    signal that a rerun-driven `flaky` verdict may reflect something other
    than a non-deterministic test (infra, setup step, dependency install)."""

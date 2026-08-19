"""`features/flaky_tests/service.py`'s `_compute_verdict` — the core
heuristic, exercised directly against constructed `WorkflowRun` rows
(never persisted, no DB needed for this level). `analyze_workflows`'s
grouping/DB query is covered separately at the integration level."""

import uuid
from datetime import UTC, datetime, timedelta

from relay_api.features.flaky_tests import service
from relay_api.features.flaky_tests.models import WorkflowRun

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _run(
    *,
    conclusion: str | None,
    status: str = "completed",
    run_attempt: int = 1,
    days_ago: int = 0,
    first_attempt_conclusion: str | None = None,
) -> WorkflowRun:
    return WorkflowRun(
        user_id=uuid.uuid4(),
        repo="acme/widgets",
        workflow_name="CI",
        run_id=1,
        run_attempt=run_attempt,
        head_branch="main",
        head_sha="abc123",
        conclusion=conclusion,
        status=status,
        html_url="https://github.com/acme/widgets/actions/runs/1",
        pull_requests=[],
        run_started_at=_BASE - timedelta(days=days_ago),
        first_attempt_conclusion=first_attempt_conclusion,
    )


def _chronological(*runs: WorkflowRun) -> list[WorkflowRun]:
    """Test cases below list runs oldest-first for readability — matches
    what `analyze_workflows` actually passes in (sorted ascending)."""
    return list(runs)


def test_no_completed_runs_is_unknown() -> None:
    runs = _chronological(_run(conclusion=None, status="in_progress", days_ago=1))

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "unknown"
    assert total == 0


def test_all_passing_with_no_reruns_is_stable() -> None:
    runs = _chronological(
        _run(conclusion="success", days_ago=3),
        _run(conclusion="success", days_ago=2),
        _run(conclusion="success", days_ago=1),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "stable"
    assert (total, passed, failed, reruns) == (3, 3, 0, 0)


def test_a_clean_failing_streak_with_no_earlier_pass_is_broken() -> None:
    # Started failing and stayed failed — reads as a real regression.
    runs = _chronological(
        _run(conclusion="success", days_ago=4),
        _run(conclusion="success", days_ago=3),
        _run(conclusion="failure", days_ago=2),
        _run(conclusion="failure", days_ago=1),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "broken"
    assert (total, passed, failed, reruns) == (4, 2, 2, 0)


def test_a_pass_after_an_earlier_failure_is_flaky() -> None:
    runs = _chronological(
        _run(conclusion="failure", days_ago=3),
        _run(conclusion="success", days_ago=2),
        _run(conclusion="failure", days_ago=1),
    )

    verdict, *_ = service._compute_verdict(runs)

    assert verdict == "flaky"


def test_a_rerun_makes_an_otherwise_stable_history_flaky() -> None:
    # The strongest signal: same commit, different result, no code change.
    runs = _chronological(
        _run(conclusion="success", days_ago=2),
        _run(conclusion="success", days_ago=1, run_attempt=2),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "flaky"
    assert reruns == 1


def test_a_rerun_that_succeeds_overrides_what_would_otherwise_read_as_broken() -> None:
    runs = _chronological(
        _run(conclusion="success", days_ago=3),
        _run(conclusion="failure", days_ago=2),
        _run(conclusion="success", days_ago=1, run_attempt=2),
    )

    verdict, *_ = service._compute_verdict(runs)

    assert verdict == "flaky"


def test_a_rerun_that_still_fails_does_not_override_a_broken_read() -> None:
    # `run_attempt > 1` alone isn't override-strength evidence — only a
    # re-run whose current outcome is `success` is (see `_compute_verdict`'s
    # docstring: the run-list API only exposes the latest attempt, so a
    # still-failing re-run is equally consistent with "genuinely broken,
    # retried out of hope" as with real flakiness). `rerun_count` still
    # counts it, but it doesn't force the verdict.
    runs = _chronological(
        _run(conclusion="success", days_ago=3),
        _run(conclusion="failure", days_ago=2),
        _run(conclusion="failure", days_ago=1, run_attempt=2),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "broken"
    assert reruns == 1


def test_a_ground_truth_flip_from_success_to_failure_is_flaky() -> None:
    # The case the assumption-only fallback can't see: a re-run whose
    # *current* conclusion is failure, but ground truth shows attempt 1
    # actually passed. Without `first_attempt_conclusion`, this would be
    # indistinguishable from "retried while already broken" and wouldn't
    # count as evidence — with it, the flip is unambiguous.
    runs = _chronological(
        _run(conclusion="success", days_ago=2),
        _run(
            conclusion="failure",
            run_attempt=2,
            first_attempt_conclusion="success",
            days_ago=1,
        ),
    )

    verdict, *_ = service._compute_verdict(runs)

    assert verdict == "flaky"


def test_a_rerun_with_ground_truth_showing_no_flip_does_not_override_broken() -> None:
    # `run_attempt > 1` alone isn't enough even with ground-truth data
    # present — attempt 1 and the current conclusion genuinely agree
    # (failed both times), so there's no flip to treat as evidence.
    runs = _chronological(
        _run(conclusion="success", days_ago=3),
        _run(conclusion="failure", days_ago=2),
        _run(
            conclusion="failure",
            run_attempt=2,
            first_attempt_conclusion="failure",
            days_ago=1,
        ),
    )

    verdict, *_ = service._compute_verdict(runs)

    assert verdict == "broken"


def test_ground_truth_overrides_the_assumption_fallback() -> None:
    # Under the assumption-only fallback, any re-run currently reading
    # `success` counts as evidence. Ground truth here shows attempt 1
    # *also* succeeded — no flip actually happened — so it must not count,
    # even though the fallback heuristic alone would have called it flaky.
    runs = _chronological(
        _run(conclusion="success", days_ago=2),
        _run(
            conclusion="success",
            run_attempt=2,
            first_attempt_conclusion="success",
            days_ago=1,
        ),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "stable"
    assert reruns == 1  # still counted for display, just not as evidence


def test_in_progress_runs_are_excluded_from_the_completed_count() -> None:
    runs = _chronological(
        _run(conclusion="success", days_ago=2),
        _run(conclusion=None, status="in_progress", days_ago=0),
    )

    verdict, total, passed, failed, reruns = service._compute_verdict(runs)

    assert verdict == "stable"
    assert total == 1  # the in-progress run doesn't count


# --- Build 2 (ADR 0019): individual test-case verdicts ---


def test_test_case_all_passing_is_stable() -> None:
    verdict, total, passed, failed = service._compute_test_case_verdict(["passed", "passed"])

    assert (verdict, total, passed, failed) == ("stable", 2, 2, 0)


def test_test_case_clean_failing_streak_is_broken() -> None:
    verdict, *_ = service._compute_test_case_verdict(["passed", "failed", "failed"])

    assert verdict == "broken"


def test_test_case_pass_after_earlier_failure_is_flaky() -> None:
    verdict, *_ = service._compute_test_case_verdict(["failed", "passed", "failed"])

    assert verdict == "flaky"


def test_test_case_no_completed_outcomes_is_unknown() -> None:
    verdict, total, *_ = service._compute_test_case_verdict(["skipped"])

    assert verdict == "unknown"
    assert total == 0


def test_test_case_skipped_outcomes_are_excluded_from_the_count() -> None:
    verdict, total, passed, failed = service._compute_test_case_verdict(
        ["passed", "skipped", "passed"]
    )

    assert (verdict, total, passed, failed) == ("stable", 2, 2, 0)

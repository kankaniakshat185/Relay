"""`jobs.flaky_tests._sync_flaky_tests_for_user` — the actual ingestion
job, run for real against Postgres with only the live GitHub calls
mocked. Same `_SameSessionCM` pattern as `test_indexing_job.py`.
"""

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.features.flaky_tests.models import CaseResult, WorkflowRun
from relay_api.jobs import flaky_tests as flaky_tests_job

_JUNIT_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="2">
  <testcase classname="tests.test_math" name="test_add" time="0.01" />
  <testcase classname="tests.test_math" name="test_subtract" time="0.02">
    <failure message="assert 1 == 2">AssertionError</failure>
  </testcase>
</testsuite>
"""


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buf.getvalue()


class _SameSessionCM:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncSession:
        return self._db

    async def __aexit__(self, *exc_info: object) -> None:
        return None


async def _connect_github(db: AsyncSession, user: User) -> None:
    db.add(
        ConnectorCredential(
            user_id=user.id,
            provider="github",
            access_token_encrypted=encrypt_token("gh-token"),
            scope="repo",
            external_account_id="1",
            external_account_label="octocat",
        )
    )
    await db.commit()


def _raw_run(
    run_id: int, conclusion: str | None, status: str = "completed", run_attempt: int = 1
) -> dict:
    return {
        "id": run_id,
        "name": "CI",
        "run_attempt": run_attempt,
        "head_branch": "main",
        "head_sha": "abc123",
        "conclusion": conclusion,
        "status": status,
        "html_url": f"https://github.com/acme/widgets/actions/runs/{run_id}",
        "pull_requests": [{"number": 7, "url": "https://api.github.com/.../pulls/7"}],
        "created_at": "2026-01-01T00:00:00Z",
    }


async def test_ingests_workflow_runs_for_a_real_connected_user(
    db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    runs = [_raw_run(1, "success"), _raw_run(2, "failure")]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=runs)
        ),
        # Both runs are `status="completed"`, so ingestion also attempts
        # the Build 2 artifact fetch for each — mocked here to "no
        # artifacts found", the same as every real repo with no
        # test-report artifact, rather than an unmocked real network call.
        patch.object(flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=[])),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.user_id == test_user.id).order_by(WorkflowRun.run_id)
    )
    rows = list(result.scalars().all())
    assert len(rows) == 2
    assert rows[0].conclusion == "success"
    assert rows[1].conclusion == "failure"
    # The real, browsable web URL — constructed, not the raw API url
    # GitHub's own payload carries in `pull_requests[].url`.
    assert rows[0].pull_requests == [{"number": 7, "url": "https://github.com/acme/widgets/pull/7"}]


async def test_resyncing_updates_an_existing_runs_conclusion(
    db: AsyncSession, test_user: User
) -> None:
    # A run that was `in_progress` when first ingested later completes —
    # the same run_id must update in place, not duplicate.
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client,
            "list_workflow_runs",
            new=AsyncMock(return_value=[_raw_run(1, None, status="in_progress")]),
        ),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client,
            "list_workflow_runs",
            new=AsyncMock(return_value=[_raw_run(1, "success", status="completed")]),
        ),
        patch.object(flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=[])),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    result = await db.execute(select(WorkflowRun).where(WorkflowRun.user_id == test_user.id))
    rows = list(result.scalars().all())
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0].status == "completed"
    assert rows[0].conclusion == "success"


# --- Build 2 (ADR 0019): individual test-case ingestion ---


async def test_ingests_test_cases_from_a_real_junit_artifact(
    db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    artifacts = [{"id": 99, "name": "test-results", "size_in_bytes": len(_JUNIT_XML)}]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client,
            "list_workflow_runs",
            new=AsyncMock(return_value=[_raw_run(1, "failure")]),
        ),
        patch.object(
            flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=artifacts)
        ),
        patch.object(
            flaky_tests_job.client,
            "download_artifact",
            new=AsyncMock(return_value=_zip_bytes({"results.xml": _JUNIT_XML})),
        ),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    run = (
        await db.execute(select(WorkflowRun).where(WorkflowRun.user_id == test_user.id))
    ).scalar_one()
    result = await db.execute(select(CaseResult).where(CaseResult.workflow_run_id == run.id))
    rows = list(result.scalars().all())
    assert len(rows) == 2
    by_name = {r.test_name: r for r in rows}
    assert by_name["test_add"].outcome == "passed"
    assert by_name["test_subtract"].outcome == "failed"


async def test_skips_an_artifact_over_the_size_limit(db: AsyncSession, test_user: User) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    oversized = [
        {
            "id": 99,
            "name": "test-results",
            "size_in_bytes": flaky_tests_job._ARTIFACT_SIZE_LIMIT_BYTES + 1,
        }
    ]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client,
            "list_workflow_runs",
            new=AsyncMock(return_value=[_raw_run(1, "failure")]),
        ),
        patch.object(
            flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=oversized)
        ),
        patch.object(flaky_tests_job.client, "download_artifact") as mock_download,
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    mock_download.assert_not_awaited()  # never even attempted


async def test_a_run_with_test_cases_already_ingested_is_not_reprocessed(
    db: AsyncSession, test_user: User
) -> None:
    # Completed runs are immutable — a resync must not re-download and
    # re-parse an artifact it already has results for.
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    artifacts = [{"id": 99, "name": "test-results", "size_in_bytes": len(_JUNIT_XML)}]
    run = [_raw_run(1, "failure")]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=run)),
        patch.object(
            flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=artifacts)
        ),
        patch.object(
            flaky_tests_job.client,
            "download_artifact",
            new=AsyncMock(return_value=_zip_bytes({"results.xml": _JUNIT_XML})),
        ),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=run)),
        patch.object(
            flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=artifacts)
        ) as mock_list_artifacts,
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    mock_list_artifacts.assert_not_awaited()  # skipped — already has results


# --- ground-truth re-run detection (ADR 0018 addendum) ---


async def test_fetches_the_first_attempts_conclusion_for_a_rerun(
    db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    runs = [_raw_run(1, "success", run_attempt=2)]

    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=runs)
        ),
        patch.object(flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=[])),
        patch.object(
            flaky_tests_job.client,
            "get_workflow_run_attempt",
            new=AsyncMock(return_value={"conclusion": "failure"}),
        ) as mock_get_attempt,
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    mock_get_attempt.assert_awaited_once_with("gh-token", "acme", "widgets", 1, 1)
    run = (
        await db.execute(select(WorkflowRun).where(WorkflowRun.user_id == test_user.id))
    ).scalar_one()
    assert run.first_attempt_conclusion == "failure"


async def test_a_reruns_first_attempt_conclusion_is_not_refetched_once_captured(
    db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    runs = [_raw_run(1, "success", run_attempt=2)]

    for _ in range(2):
        with (
            patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
            patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
            patch.object(
                flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
            ),
            patch.object(
                flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=runs)
            ),
            patch.object(
                flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=[])
            ),
            patch.object(
                flaky_tests_job.client,
                "get_workflow_run_attempt",
                new=AsyncMock(return_value={"conclusion": "failure"}),
            ) as mock_get_attempt,
        ):
            await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    # Second sync must not re-fetch — attempt 1's outcome is immutable
    # and was already captured on the first sync.
    mock_get_attempt.assert_not_awaited()


async def test_a_failed_attempt_fetch_leaves_first_attempt_conclusion_none(
    db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    repos = [{"full_name": "acme/widgets", "owner": {"login": "acme"}, "name": "widgets"}]
    runs = [_raw_run(1, "success", run_attempt=2)]

    request = httpx.Request(
        "GET", "https://api.github.com/repos/acme/widgets/actions/runs/1/attempts/1"
    )
    with (
        patch.object(flaky_tests_job, "engine", new=MagicMock(dispose=AsyncMock())),
        patch.object(flaky_tests_job, "async_session_factory", return_value=_SameSessionCM(db)),
        patch.object(
            flaky_tests_job.client, "list_recent_repos", new=AsyncMock(return_value=repos)
        ),
        patch.object(
            flaky_tests_job.client, "list_workflow_runs", new=AsyncMock(return_value=runs)
        ),
        patch.object(flaky_tests_job.client, "list_run_artifacts", new=AsyncMock(return_value=[])),
        patch.object(
            flaky_tests_job.client,
            "get_workflow_run_attempt",
            new=AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "not found", request=request, response=httpx.Response(404, request=request)
                )
            ),
        ),
    ):
        await flaky_tests_job._sync_flaky_tests_for_user(test_user.id)

    run = (
        await db.execute(select(WorkflowRun).where(WorkflowRun.user_id == test_user.id))
    ).scalar_one()
    assert run.first_attempt_conclusion is None

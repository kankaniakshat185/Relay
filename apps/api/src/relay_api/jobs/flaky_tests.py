"""Celery task that polls GitHub Actions workflow-run history for each
connected user — the ingestion half of the Flaky Test Investigator (ADR
0018). Deliberately separate from `jobs/indexing.py`: different data flow
(writes `features.flaky_tests.models.WorkflowRun`, not `ingested_items`),
matching plan.md's "standalone subsystem, own historical-pattern store"
call for this feature specifically.
"""

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.connectors import service as connector_service
from relay_api.connectors.github import client
from relay_api.core.db import async_session_factory, engine
from relay_api.core.logging import get_logger
from relay_api.features.flaky_tests import junit_parser
from relay_api.features.flaky_tests.models import CaseResult, WorkflowRun
from relay_api.jobs.celery_app import celery_app

logger = get_logger(__name__)

_REPO_LIMIT = 25
"""Same value as `connectors/github/ingest.py`'s own `_REPO_LIMIT`, kept
as an independent constant rather than imported — that one is
module-private by convention, and this module's repo scope is allowed to
diverge from ingestion's own even though it matches today."""

_RUN_FETCH_LIMIT = 50
"""Recent runs fetched per repo, one API call (`per_page` — GitHub's own
page-size ceiling is 100). Bounds both request cost and the window
`features.flaky_tests.service.analyze_workflows` reasons over — same
"one page of recent activity is enough" judgment as `connectors/github/
ingest.py`'s commit/PR limits."""

_ARTIFACT_FETCH_LIMIT = 10
"""Build 2 (ADR 0019): fewer than `_RUN_FETCH_LIMIT`, and **per workflow**,
not per repo — downloading and parsing an artifact is a real file
transfer + unzip + XML parse, heavier than listing run metadata, and a
per-repo cap would let one frequently-run workflow starve every other
workflow in the same repo of any test-case data. Best-effort either way:
a repo whose workflows don't upload a JUnit-shaped artifact costs nothing
beyond the initial "no artifacts found" list call."""

_ARTIFACT_SIZE_LIMIT_BYTES = 5 * 1024 * 1024
"""Skip downloading an artifact bigger than this (checked against
`list_run_artifacts`' own `size_in_bytes`, before any download starts) —
real JUnit XML is structured text, even a large test suite's report
comfortably fits well under this; an artifact this big is very unlikely
to be a test report at all."""

_ATTEMPT_FETCH_LIMIT = 20
"""Per repo, per sync: how many re-runs (`run_attempt > 1`) get their
attempt-1 outcome fetched via `get_workflow_run_attempt` (ADR 0018's
ground-truth re-run layer). Re-runs are rare relative to total runs, so
this is generous compared to `_ARTIFACT_FETCH_LIMIT` — the call itself is
a single small JSON response, not a download+unzip+parse — but still
bounded: a repo with an unusually large number of re-runs in one sync
shouldn't be able to blow the sync's request budget."""


def _parse_run(raw: dict[str, Any], user_id: uuid.UUID, repo_full_name: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "repo": repo_full_name,
        "workflow_name": raw.get("name") or "(unnamed workflow)",
        "run_id": raw["id"],
        "run_attempt": raw.get("run_attempt", 1),
        "head_branch": raw.get("head_branch") or "",
        "head_sha": raw["head_sha"],
        "conclusion": raw.get("conclusion"),
        "status": raw["status"],
        "html_url": raw["html_url"],
        # GitHub's own `pull_requests[].url` on a workflow run is the API
        # endpoint (`https://api.github.com/repos/.../pulls/N`), not a
        # browsable page — there's no `html_url` in that minimal PR
        # reference object at all, so the real web URL is built from
        # parts already in hand rather than trusted from the payload.
        "pull_requests": [
            {
                "number": pr["number"],
                "url": f"https://github.com/{repo_full_name}/pull/{pr['number']}",
            }
            for pr in (raw.get("pull_requests") or [])
        ],
        "run_started_at": datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
    }


async def _ingest_test_cases_for_run(
    db: AsyncSession, access_token: str, owner: str, repo: str, run_db_id: uuid.UUID, gh_run_id: int
) -> int:
    """Best-effort: tries each artifact attached to the run until one
    parses as a JUnit-shaped report, stores its test cases, and stops.
    Returns the number of test cases ingested — 0 is the common,
    expected outcome for a run whose workflow doesn't produce a
    JUnit-style artifact at all, not a failure."""
    try:
        artifacts = await client.list_run_artifacts(access_token, owner, repo, gh_run_id)
    except httpx.HTTPStatusError:
        return 0

    for artifact in artifacts:
        if artifact.get("size_in_bytes", 0) > _ARTIFACT_SIZE_LIMIT_BYTES:
            continue
        try:
            zip_bytes = await client.download_artifact(access_token, owner, repo, artifact["id"])
        except httpx.HTTPStatusError:
            continue

        outcomes = junit_parser.find_and_parse_junit_report(zip_bytes)
        if not outcomes:
            continue

        for outcome in outcomes:
            stmt = (
                insert(CaseResult)
                .values(
                    workflow_run_id=run_db_id,
                    classname=outcome.classname,
                    test_name=outcome.name,
                    outcome=outcome.outcome,
                    duration_seconds=outcome.duration_seconds,
                )
                .on_conflict_do_nothing(constraint="uq_flaky_test_case_run_name")
            )
            await db.execute(stmt)
        return len(outcomes)

    return 0


async def _ingest_first_attempt_conclusion(
    db: AsyncSession, access_token: str, owner: str, repo: str, run_db_id: uuid.UUID, gh_run_id: int
) -> None:
    """Best-effort: fetches attempt 1's real `conclusion` for a re-run and
    stores it, so `service._rerun_is_flaky_evidence` can compare it
    against the run's current conclusion instead of assuming. Never
    raises — a failed fetch just leaves `first_attempt_conclusion` `None`,
    which is already the fallback-to-assumption case."""
    try:
        attempt = await client.get_workflow_run_attempt(access_token, owner, repo, gh_run_id, 1)
    except httpx.HTTPStatusError:
        return

    first_conclusion = attempt.get("conclusion")
    if first_conclusion is None:
        return
    await db.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_db_id)
        .values(first_attempt_conclusion=first_conclusion)
    )


async def _sync_flaky_tests_for_user(user_id: uuid.UUID) -> None:
    # Same fix, same reason as jobs/indexing.py's `_run_indexing_for_connector`
    # — Celery's prefork workers reuse the same process across many tasks,
    # each spinning up its own event loop via `asyncio.run`; disposing the
    # engine forces fresh connections bound to *this* task's loop.
    await engine.dispose()

    async with async_session_factory() as db:
        credential = await connector_service.get_credential(db, user_id, "github")
        if credential is None:
            return

        try:
            access_token = await connector_service.ensure_valid_access_token(db, credential)
        except connector_service.TokenRefreshError:
            logger.warning("flaky_tests_sync_token_refresh_failed", extra={"user_id": str(user_id)})
            return

        repos = await client.list_recent_repos(access_token, limit=_REPO_LIMIT)

        total_runs = 0
        total_test_cases = 0
        for repo in repos:
            repo_full_name = repo["full_name"]
            owner, name = repo["owner"]["login"], repo["name"]
            raw_runs = await client.list_workflow_runs(
                access_token, owner, name, per_page=_RUN_FETCH_LIMIT
            )

            # (workflow_name -> [(db id, github run id, started_at), ...])
            # for completed runs only — in-progress/queued runs have
            # nothing to fetch a test report for yet.
            completed_by_workflow: dict[str, list[tuple[uuid.UUID, int, datetime]]] = defaultdict(
                list
            )
            attempt_fetches_used = 0
            for raw in raw_runs:
                row = _parse_run(raw, user_id, repo_full_name)
                stmt = (
                    insert(WorkflowRun)
                    .values(**row)
                    .on_conflict_do_update(
                        constraint="uq_flaky_run_user_repo_run_id",
                        set_={
                            "conclusion": row["conclusion"],
                            "status": row["status"],
                            "run_attempt": row["run_attempt"],
                            "pull_requests": row["pull_requests"],
                        },
                    )
                    .returning(WorkflowRun.id, WorkflowRun.first_attempt_conclusion)
                )
                run_db_id, existing_first_attempt_conclusion = (await db.execute(stmt)).one()
                total_runs += 1
                if row["status"] == "completed":
                    completed_by_workflow[row["workflow_name"]].append(
                        (run_db_id, row["run_id"], row["run_started_at"])
                    )

                # Ground-truth re-run detection (ADR 0018 addendum):
                # best-effort, capped, and never re-fetched once captured
                # — a re-run's attempt-1 outcome is immutable, same
                # reasoning as `CaseResult`'s "processed once" check below.
                if (
                    row["run_attempt"] > 1
                    and existing_first_attempt_conclusion is None
                    and attempt_fetches_used < _ATTEMPT_FETCH_LIMIT
                ):
                    await _ingest_first_attempt_conclusion(
                        db, access_token, owner, name, run_db_id, row["run_id"]
                    )
                    attempt_fetches_used += 1

            # Build 2 (ADR 0019): best-effort test-case detail for the
            # most recent completed runs *per workflow* that don't have
            # it yet — skips runs already processed by an earlier sync,
            # so a completed run's (immutable) test results are only
            # ever downloaded and parsed once.
            for entries in completed_by_workflow.values():
                entries.sort(key=lambda e: e[2], reverse=True)
                for run_db_id, gh_run_id, _started_at in entries[:_ARTIFACT_FETCH_LIMIT]:
                    already_has_results = await db.scalar(
                        select(CaseResult.id)
                        .where(CaseResult.workflow_run_id == run_db_id)
                        .limit(1)
                    )
                    if already_has_results is not None:
                        continue
                    total_test_cases += await _ingest_test_cases_for_run(
                        db, access_token, owner, name, run_db_id, gh_run_id
                    )

        await db.commit()

        logger.info(
            "flaky_tests_sync_completed",
            extra={
                "user_id": str(user_id),
                "repos": len(repos),
                "runs": total_runs,
                "test_cases": total_test_cases,
            },
        )


@celery_app.task(name="relay_api.jobs.flaky_tests.sync_flaky_tests_task")
def sync_flaky_tests_task(user_id: str) -> None:
    asyncio.run(_sync_flaky_tests_for_user(uuid.UUID(user_id)))


async def _enqueue_flaky_tests_sync_for_all_users() -> int:
    await engine.dispose()

    async with async_session_factory() as db:
        credentials = await connector_service.list_all_credentials(db)

    # One task per user (not per user+provider like jobs/indexing.py's
    # resync) — this feature only ever reads GitHub, so "connected to
    # GitHub" is the only thing that matters here.
    user_ids = {c.user_id for c in credentials if c.provider == "github"}
    for user_id in user_ids:
        sync_flaky_tests_task.delay(str(user_id))

    return len(user_ids)


@celery_app.task(name="relay_api.jobs.flaky_tests.resync_all_flaky_tests_task")
def resync_all_flaky_tests_task() -> None:
    """Celery Beat fires this on the same 15-minute schedule as
    `jobs.indexing.resync_all_connectors_task` (see `celery_app.py`) —
    separate task, separate beat entry, so a failure in one sync doesn't
    affect the other."""
    count = asyncio.run(_enqueue_flaky_tests_sync_for_all_users())
    logger.info("flaky_tests_resync_all_enqueued", extra={"count": count})

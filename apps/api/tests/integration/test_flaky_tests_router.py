"""Router-level: real DB and real `analyze_workflows` grouping/verdict
logic over rows inserted directly (no live GitHub call needed for
`/workflows` — it only reads already-ingested `WorkflowRun` rows).
`/repos` mirrors Archaeology/Who Should I Ask's own `/repos` test shape.
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.core.deps import get_current_user
from relay_api.features.flaky_tests.models import CaseResult, WorkflowRun
from relay_api.main import app


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


async def test_repos_requires_github_to_be_connected(client: AsyncClient, test_user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.get("/v1/flaky-tests/repos")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400


async def test_workflows_returns_verdicts_for_a_real_connected_user(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)

    for run_id, conclusion, days_ago in [(1, "success", 3), (2, "success", 2), (3, "success", 1)]:
        db.add(
            WorkflowRun(
                user_id=test_user.id,
                repo="acme/widgets",
                workflow_name="CI",
                run_id=run_id,
                run_attempt=1,
                head_branch="main",
                head_sha="abc123",
                conclusion=conclusion,
                status="completed",
                html_url=f"https://github.com/acme/widgets/actions/runs/{run_id}",
                pull_requests=[],
                run_started_at=datetime(2026, 1, 1, tzinfo=UTC) - timedelta(days=days_ago),
            )
        )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.get(
            "/v1/flaky-tests/workflows", params={"owner": "acme", "repo": "widgets"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    workflows = response.json()
    assert len(workflows) == 1
    assert workflows[0]["workflow_name"] == "CI"
    assert workflows[0]["verdict"] == "stable"
    assert workflows[0]["total_considered"] == 3
    assert workflows[0]["has_test_case_data"] is False


async def test_workflows_is_scoped_to_the_requested_repo(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    await _connect_github(db, test_user)
    db.add(
        WorkflowRun(
            user_id=test_user.id,
            repo="acme/other-repo",
            workflow_name="CI",
            run_id=1,
            run_attempt=1,
            head_branch="main",
            head_sha="abc123",
            conclusion="success",
            status="completed",
            html_url="https://github.com/acme/other-repo/actions/runs/1",
            pull_requests=[],
            run_started_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.get(
            "/v1/flaky-tests/workflows", params={"owner": "acme", "repo": "widgets"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == []


async def test_workflows_surfaces_flaky_individual_test_cases(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """Build 2 (ADR 0019), end to end: real `CaseResult` rows across two
    runs, one test that flips pass/fail, one that's consistently stable
    — only the flaky one should show up in `flaky_test_cases`."""
    await _connect_github(db, test_user)

    run_ids = []
    for run_id, conclusion, days_ago in [(1, "failure", 2), (2, "success", 1)]:
        run = WorkflowRun(
            user_id=test_user.id,
            repo="acme/widgets",
            workflow_name="CI",
            run_id=run_id,
            run_attempt=1,
            head_branch="main",
            head_sha="abc123",
            conclusion=conclusion,
            status="completed",
            html_url=f"https://github.com/acme/widgets/actions/runs/{run_id}",
            pull_requests=[],
            run_started_at=datetime(2026, 1, 1, tzinfo=UTC) - timedelta(days=days_ago),
        )
        db.add(run)
        await db.flush()
        run_ids.append(run.id)

    # test_flaky: failed on the older run, passed on the newer one.
    db.add(
        CaseResult(
            workflow_run_id=run_ids[0],
            classname="tests.test_math",
            test_name="test_flaky",
            outcome="failed",
        )
    )
    db.add(
        CaseResult(
            workflow_run_id=run_ids[1],
            classname="tests.test_math",
            test_name="test_flaky",
            outcome="passed",
        )
    )
    # test_stable: passed on both.
    db.add(
        CaseResult(
            workflow_run_id=run_ids[0],
            classname="tests.test_math",
            test_name="test_stable",
            outcome="passed",
        )
    )
    db.add(
        CaseResult(
            workflow_run_id=run_ids[1],
            classname="tests.test_math",
            test_name="test_stable",
            outcome="passed",
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.get(
            "/v1/flaky-tests/workflows", params={"owner": "acme", "repo": "widgets"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    workflow = response.json()[0]
    flaky_cases = workflow["flaky_test_cases"]
    assert len(flaky_cases) == 1
    assert flaky_cases[0]["test_name"] == "test_flaky"
    assert flaky_cases[0]["verdict"] == "flaky"
    assert workflow["has_test_case_data"] is True


async def test_a_rerun_driven_flaky_verdict_with_no_confirming_test_case_is_marked_unconfirmed(
    client: AsyncClient, db: AsyncSession, test_user: User
) -> None:
    """The verdict is `flaky` on the rerun signal alone; every captured
    test case is consistently stable across both runs. `has_test_case_data`
    should still be `True` (we did capture data) even though
    `flaky_test_cases` is empty — the cross-check this test proves out."""
    await _connect_github(db, test_user)

    run_ids = []
    for run_id, conclusion, run_attempt, days_ago in [
        (1, "success", 1, 2),
        (2, "success", 2, 1),
    ]:
        run = WorkflowRun(
            user_id=test_user.id,
            repo="acme/widgets",
            workflow_name="CI",
            run_id=run_id,
            run_attempt=run_attempt,
            head_branch="main",
            head_sha="abc123",
            conclusion=conclusion,
            status="completed",
            html_url=f"https://github.com/acme/widgets/actions/runs/{run_id}",
            pull_requests=[],
            run_started_at=datetime(2026, 1, 1, tzinfo=UTC) - timedelta(days=days_ago),
        )
        db.add(run)
        await db.flush()
        run_ids.append(run.id)

    for rid in run_ids:
        db.add(
            CaseResult(
                workflow_run_id=rid,
                classname="tests.test_math",
                test_name="test_stable",
                outcome="passed",
            )
        )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: test_user
    try:
        response = await client.get(
            "/v1/flaky-tests/workflows", params={"owner": "acme", "repo": "widgets"}
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    workflow = response.json()[0]
    assert workflow["verdict"] == "flaky"
    assert workflow["rerun_count"] == 1
    assert workflow["flaky_test_cases"] == []
    assert workflow["has_test_case_data"] is True

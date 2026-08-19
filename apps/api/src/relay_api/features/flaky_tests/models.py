"""`flaky_test_workflow_runs` — this feature's own historical-pattern
store, deliberately separate from `engine.ingestion`'s shared
`ingested_items` table. plan.md scopes Flaky Test Investigator as a
standalone subsystem for exactly this reason ("integrates cleanly
without polluting the core engine") — see ADR 0018.

Column ownership: `jobs/flaky_tests.py` is the only writer (polls GitHub
Actions, upserts here); `features/flaky_tests/service.py` is the only
reader.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from relay_api.core.db import Base


class WorkflowRun(Base):
    __tablename__ = "flaky_test_workflow_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "repo", "run_id", name="uq_flaky_run_user_repo_run_id"),
        Index("ix_flaky_run_user_repo", "user_id", "repo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    repo: Mapped[str] = mapped_column(String(255))
    """`"owner/name"` — matches the same denormalized shape
    `connectors/github/normalize.py` already uses for `extra.repo`."""
    workflow_name: Mapped[str] = mapped_column(String(255))
    run_id: Mapped[int] = mapped_column(BigInteger)
    """GitHub's own numeric run id — the identity key alongside
    (user_id, repo). `BigInteger`, not `Integer`: real run ids on active
    repos routinely exceed 32-bit range."""
    run_attempt: Mapped[int] = mapped_column(Integer, default=1)
    """> 1 means this is a re-run of a previous attempt on the same
    commit — a strong flakiness signal on its own (see
    `service.analyze_workflows`)."""
    head_branch: Mapped[str] = mapped_column(String(255))
    head_sha: Mapped[str] = mapped_column(String(40))
    conclusion: Mapped[str | None] = mapped_column(String(32), default=None)
    """success | failure | cancelled | skipped | timed_out | ... | `None`
    while `status` isn't yet `completed`."""
    first_attempt_conclusion: Mapped[str | None] = mapped_column(String(32), default=None)
    """Ground truth for what attempt 1 of this run actually concluded —
    only populated for re-runs (`run_attempt > 1`), via a dedicated
    best-effort fetch (`jobs.flaky_tests`, capped by `_ATTEMPT_FETCH_LIMIT`)
    of GitHub's per-attempt endpoint. `None` means either this run was
    never a re-run, or its attempt-1 outcome wasn't fetched (rate-limited,
    capped, or the fetch itself failed) — `service._rerun_is_flaky_evidence`
    falls back to an assumption-based proxy in that case. Immutable once
    set (attempt 1 already happened and its outcome can't change), so a
    resync never re-fetches it — same discipline as `CaseResult`."""
    status: Mapped[str] = mapped_column(String(32))
    """queued | in_progress | completed."""
    html_url: Mapped[str] = mapped_column(String(2048))
    pull_requests: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    """Denormalized `[{number, url}]` straight from the run's own GitHub
    payload — plan.md's "recent related PRs" comes for free from this,
    no correlation call needed."""
    run_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CaseResult(Base):
    """Build 2 (ADR 0019) — individual test-case outcomes, populated only
    when a JUnit-shaped test-report artifact was found and parsed for a
    run. A `WorkflowRun` with no `CaseResult` rows simply has no
    captured test-case detail; that's the common, expected case for a
    repo whose workflows don't upload one, not a gap to fill in later."""

    __tablename__ = "flaky_test_case_results"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "classname", "test_name", name="uq_flaky_test_case_run_name"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("flaky_test_workflow_runs.id", ondelete="CASCADE"), index=True
    )

    classname: Mapped[str] = mapped_column(String(512))
    test_name: Mapped[str] = mapped_column(String(512))
    outcome: Mapped[str] = mapped_column(String(16))
    """`"passed" | "failed" | "skipped"` — see `junit_parser.TestCaseOutcome`."""
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

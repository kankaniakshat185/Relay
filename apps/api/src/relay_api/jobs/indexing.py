"""Celery task that runs after a connector is connected (see
`connectors/router.py`'s callback): fetch → normalize → ingest → index for
one user's one provider. Each connector's `ingest.fetch_normalized_items`
already returns the common `NormalizedItem` shape (`engine/ingestion`), so
this orchestration layer stays provider-agnostic past the initial dispatch.
"""

import asyncio
import uuid

from relay_api.connectors import service as connector_service
from relay_api.connectors.github import ingest as github_ingest
from relay_api.connectors.jira import ingest as jira_ingest
from relay_api.connectors.models import ConnectorCredential
from relay_api.connectors.slack import ingest as slack_ingest
from relay_api.core.db import async_session_factory, engine
from relay_api.core.logging import get_logger
from relay_api.engine.indexing import service as indexing_service
from relay_api.engine.ingestion import service as ingestion_service
from relay_api.engine.ingestion.schemas import NormalizedItem
from relay_api.jobs.celery_app import celery_app

logger = get_logger(__name__)


async def _fetch_items(
    provider: str, access_token: str, credential: ConnectorCredential
) -> list[NormalizedItem]:
    if provider == "github":
        return await github_ingest.fetch_normalized_items(access_token)
    if provider == "slack":
        return await slack_ingest.fetch_normalized_items(
            access_token, credential.external_account_id
        )
    if provider == "jira":
        return await jira_ingest.fetch_normalized_items(
            access_token, credential.external_account_id, credential.external_account_label
        )
    raise ValueError(f"Unknown connector provider: {provider}")


async def _run_indexing_for_connector(user_id: uuid.UUID, provider: str) -> None:
    # `core/db.py`'s engine is a module-level singleton — correct for
    # FastAPI, which keeps one event loop for the process's whole
    # lifetime. Celery's prefork workers don't: the same worker child
    # process handles many tasks over its life, and `index_connector_task`
    # below calls `asyncio.run(...)`, which spins up a *new* event loop
    # every single task. The engine's connection pool binds to whichever
    # loop first touches it; the next task in that same worker process
    # then hands the pool a stale, already-closed loop and asyncpg blows
    # up with "attached to a different loop". Found live: GitHub and Slack
    # indexing (each worker process's first task) worked fine; Jira's
    # retry, routed to an already-used worker process, silently failed
    # with zero rows ever reaching the DB. Disposing the pool at the start
    # of every task forces fresh connections bound to *this* task's loop —
    # SQLAlchemy's own documented fix for exactly this asyncio-multi-loop
    # scenario.
    await engine.dispose()

    async with async_session_factory() as db:
        credential = await connector_service.get_credential(db, user_id, provider)
        if credential is None:
            logger.warning(
                "index_job_no_credential", extra={"user_id": str(user_id), "provider": provider}
            )
            return

        try:
            access_token = await connector_service.ensure_valid_access_token(db, credential)
        except connector_service.TokenRefreshError:
            # The refresh grant itself failed (revoked/expired refresh
            # token) — not something to retry from inside this task.
            # Reconnecting via the Connections page is the recovery path.
            logger.warning(
                "index_job_token_refresh_failed",
                extra={"user_id": str(user_id), "provider": provider},
            )
            return

        items = await _fetch_items(provider, access_token, credential)

        await ingestion_service.upsert_items(db, user_id, items)
        to_index = await ingestion_service.get_items_needing_indexing(db, user_id)
        await indexing_service.index_items(db, to_index)

        logger.info(
            "index_job_completed",
            extra={
                "user_id": str(user_id),
                "provider": provider,
                "ingested": len(items),
                "indexed": len(to_index),
            },
        )


@celery_app.task(name="relay_api.jobs.indexing.index_connector_task")
def index_connector_task(user_id: str, provider: str) -> None:
    asyncio.run(_run_indexing_for_connector(uuid.UUID(user_id), provider))


async def _enqueue_resync_for_all_connectors() -> int:
    # Same dispose-before-use fix as `_run_indexing_for_connector`, and for
    # the same reason: Celery Beat fires this task in a worker process that
    # may have already run other async DB work on a now-closed loop.
    await engine.dispose()

    async with async_session_factory() as db:
        credentials = await connector_service.list_all_credentials(db)

    for credential in credentials:
        index_connector_task.delay(str(credential.user_id), credential.provider)

    return len(credentials)


@celery_app.task(name="relay_api.jobs.indexing.resync_all_connectors_task")
def resync_all_connectors_task() -> None:
    """Celery Beat fires this on a schedule (see `celery_app.py`) — the fix
    for indexing otherwise only ever running once, at connect time (found
    live: a Slack message posted after the initial connect was never
    searchable until this existed, since nothing re-ran ingestion for it).

    Deliberately thin: reads who's connected to what, then re-enqueues the
    existing per-connector task for each — no indexing logic duplicated
    here, and every provider gets the same treatment for free, since
    `index_connector_task` was already provider-agnostic.
    """
    count = asyncio.run(_enqueue_resync_for_all_connectors())
    logger.info("resync_all_connectors_enqueued", extra={"count": count})

"""App factory + router registration ONLY — no business logic lives here.

See plan.md §2: main.py wires things together; everything else lives in
`core/`, `auth/`, `connectors/`, `engine/`, and `features/`.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from relay_api.auth.router import router as auth_router
from relay_api.connectors.router import router as connectors_router
from relay_api.core.config import get_settings
from relay_api.core.logging import configure_logging, get_logger
from relay_api.engine.indexing.embeddings import EmbeddingUnavailableError
from relay_api.features.context_search.router import router as context_search_router

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    logger.info("relay_api_startup", extra={"env": settings.env})
    yield
    logger.info("relay_api_shutdown")


def create_app() -> FastAPI:
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)

    app = FastAPI(title="Relay API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    v1 = APIRouter(prefix=settings.api_v1_prefix)
    v1.include_router(auth_router)
    v1.include_router(connectors_router)
    v1.include_router(context_search_router)
    # Phase 2+: archaeology, who_to_ask routers — see plan.md §5.
    app.include_router(v1)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(EmbeddingUnavailableError)
    async def embedding_unavailable_handler(
        _request: Request, exc: EmbeddingUnavailableError
    ) -> JSONResponse:
        # Every search and indexing run depends on embeddings unconditionally
        # (ADR 0006/0008) — a failure here is "the feature is down", not
        # something to fall back from. Logged with the real cause; the
        # client gets a clean message instead of a raw 500 + stack trace.
        logger.warning("embedding_unavailable", extra={"error": str(exc)})
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Search is temporarily unavailable — the embeddings "
                "provider had an error. Try again shortly."
            },
        )

    return app


app = create_app()

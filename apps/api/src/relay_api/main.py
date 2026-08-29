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
from relay_api.auth.service import OAuthExchangeError
from relay_api.connectors.base import ConnectorExchangeError
from relay_api.connectors.router import router as connectors_router
from relay_api.connectors.service import ConnectorNotConnectedError, TokenRefreshError
from relay_api.core.config import get_settings
from relay_api.core.logging import configure_logging, get_logger
from relay_api.engine.code_context.service import CodeContextError
from relay_api.engine.indexing.embeddings import EmbeddingUnavailableError
from relay_api.features.archaeology.router import router as archaeology_router
from relay_api.features.context_search.router import router as context_search_router
from relay_api.features.flaky_tests.router import router as flaky_tests_router
from relay_api.features.notes.router import router as notes_router
from relay_api.features.weekly_digest.router import router as weekly_digest_router
from relay_api.features.who_to_ask.router import router as who_to_ask_router

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
    v1.include_router(archaeology_router)
    v1.include_router(who_to_ask_router)
    v1.include_router(flaky_tests_router)
    v1.include_router(notes_router)
    v1.include_router(weekly_digest_router)
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

    @app.exception_handler(ConnectorNotConnectedError)
    async def connector_not_connected_handler(
        _request: Request, exc: ConnectorNotConnectedError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Connect {exc.provider.capitalize()} first to use this feature."},
        )

    @app.exception_handler(TokenRefreshError)
    async def token_refresh_error_handler(
        _request: Request, exc: TokenRefreshError
    ) -> JSONResponse:
        # Found live: a rejected refresh grant (revoked/expired refresh
        # token, or a provider that just rejects it without a clear
        # reason — GitHub, sometimes) used to propagate unhandled all the
        # way to the client as a raw network-level failure, not even a
        # real HTTP response. See the Phase 2 retro.
        logger.warning("token_refresh_error", extra={"error": str(exc)})
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Your {exc.provider.capitalize()} connection needs to be refreshed — "
                "reconnect it on the Connections page."
            },
        )

    @app.exception_handler(OAuthExchangeError)
    async def oauth_exchange_error_handler(
        _request: Request, exc: OAuthExchangeError
    ) -> JSONResponse:
        # Found live: GitHub's classic OAuth token endpoint returns HTTP
        # 200 even on failure (an `error` field in the body, not
        # `access_token`), so this used to surface as a raw 500 with the
        # real reason (stale client secret, reused/expired code, etc.)
        # silently swallowed by an unhandled KeyError. Logged with the
        # real reason; the client gets a clean 400, not a stack trace.
        logger.warning("oauth_exchange_error", extra={"error": str(exc)})
        return JSONResponse(
            status_code=400,
            content={"detail": "Sign-in failed — the provider rejected the request. Try again."},
        )

    @app.exception_handler(ConnectorExchangeError)
    async def connector_exchange_error_handler(
        _request: Request, exc: ConnectorExchangeError
    ) -> JSONResponse:
        # Found live: every provider's own `exchange_code` already checks
        # for a 200-with-error-body response (GitHub's `error` field,
        # Slack's `ok: false`) and raises for it, but nothing caught that
        # exception here — a real connect failure (stale client secret,
        # the wrong app's redirect URL registered, a reused/expired code)
        # surfaced as a raw 500 with no real reason, same class of bug
        # `OAuthExchangeError` above already fixed for the login flow.
        logger.warning("connector_exchange_error", extra={"error": str(exc)})
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Couldn't connect — the provider rejected the request. "
                "Check the connector's credentials and try again."
            },
        )

    @app.exception_handler(CodeContextError)
    async def code_context_error_handler(_request: Request, exc: CodeContextError) -> JSONResponse:
        logger.warning("code_context_error", extra={"error": str(exc)})
        return JSONResponse(
            status_code=404,
            content={
                "detail": "Couldn't complete that GitHub request — check the repo, branch, and "
                "path, or reconnect GitHub on the Connections page if your session expired."
            },
        )

    return app


app = create_app()

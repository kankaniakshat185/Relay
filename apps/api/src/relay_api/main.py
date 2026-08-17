"""App factory + router registration ONLY — no business logic lives here.

See plan.md §2: main.py wires things together; everything else lives in
`core/`, `auth/`, `connectors/`, `engine/`, and `features/`.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from relay_api.auth.router import router as auth_router
from relay_api.core.config import get_settings
from relay_api.core.logging import configure_logging, get_logger

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
    # Phase 1+: v1.include_router(context_search_router), etc. — see plan.md §5.
    app.include_router(v1)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

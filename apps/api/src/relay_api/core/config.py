"""Application configuration, loaded from environment variables.

Single source of truth for settings — nothing else in the app should read
`os.environ` directly. See `.env.example` for the full list of variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    env: str = Field(default="development", alias="ENV")
    api_v1_prefix: str = "/v1"
    # No `api_base_url` — OAuth redirect URIs point at `frontend_url`'s
    # `/api` proxy (ADR 0024), and this service is never addressed by the
    # browser directly, only by the frontend's rewrite and the Celery
    # worker's own internal calls (which don't need this setting either).
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # --- Security ---
    secret_key: str = Field(alias="SECRET_KEY")
    session_cookie_name: str = "relay_session"
    session_token_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days
    # Fernet key for connector_credentials at-rest encryption — separate
    # from secret_key, see connectors/encryption.py. Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    connector_encryption_key: str = Field(alias="CONNECTOR_ENCRYPTION_KEY")

    # --- Database ---
    database_url: str = Field(alias="DATABASE_URL")

    # --- Redis / Celery ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- OAuth: login providers (minimal scopes, identity only) ---
    github_login_client_id: str = Field(default="", alias="GITHUB_LOGIN_CLIENT_ID")
    github_login_client_secret: str = Field(default="", alias="GITHUB_LOGIN_CLIENT_SECRET")

    slack_login_client_id: str = Field(default="", alias="SLACK_LOGIN_CLIENT_ID")
    slack_login_client_secret: str = Field(default="", alias="SLACK_LOGIN_CLIENT_SECRET")

    google_login_client_id: str = Field(default="", alias="GOOGLE_LOGIN_CLIENT_ID")
    google_login_client_secret: str = Field(default="", alias="GOOGLE_LOGIN_CLIENT_SECRET")

    # --- OAuth: connector providers (broad, data-access scopes) ---
    github_connector_client_id: str = Field(default="", alias="GITHUB_CONNECTOR_CLIENT_ID")
    github_connector_client_secret: str = Field(default="", alias="GITHUB_CONNECTOR_CLIENT_SECRET")

    slack_connector_client_id: str = Field(default="", alias="SLACK_CONNECTOR_CLIENT_ID")
    slack_connector_client_secret: str = Field(default="", alias="SLACK_CONNECTOR_CLIENT_SECRET")

    jira_connector_client_id: str = Field(default="", alias="JIRA_CONNECTOR_CLIENT_ID")
    jira_connector_client_secret: str = Field(default="", alias="JIRA_CONNECTOR_CLIENT_SECRET")

    # --- OpenAI: embeddings (ADR 0006, always server-funded) + the
    # free-tier context-search synthesis default (ADR 0007) ---
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    embedding_model: str = "text-embedding-3-small"
    synthesis_model: str = "gpt-4o-mini"

    # --- Embedding provider switch (ADR 0009). Unlike synthesis, this is
    # NOT per-request BYOK — embeddings are unconditional core infra
    # (every search and every indexing run needs one), so this is a
    # server-wide setting, not something a request chooses. "gemini" is a
    # genuinely free stand-in (no billing account needed) for testing
    # before OpenAI billing is set up; switching back later means flipping
    # this one value, no code change. ---
    embedding_provider: Literal["openai", "gemini"] = Field(
        default="openai", alias="EMBEDDING_PROVIDER"
    )
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_embedding_model: str = "gemini-embedding-001"

    # --- BYOK synthesis model defaults, one per provider (ADR 0008).
    # Only used when the request supplies its own key for that provider —
    # the free tier is OpenAI-only, these are never paid for by Relay. ---
    groq_synthesis_model: str = "llama-3.3-70b-versatile"
    anthropic_synthesis_model: str = "claude-haiku-4-5-20251001"
    gemini_synthesis_model: str = "gemini-2.5-flash"

    # Free-tier LLM-mode calls per user per day, using the server's own
    # key. BYOK requests bypass this entirely — see ADR 0008.
    free_llm_daily_limit: int = Field(default=5, alias="FREE_LLM_DAILY_LIMIT")

    # --- Observability ---
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

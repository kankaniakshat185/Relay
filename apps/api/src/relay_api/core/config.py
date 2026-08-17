"""Application configuration, loaded from environment variables.

Single source of truth for settings — nothing else in the app should read
`os.environ` directly. See `.env.example` for the full list of variables.
"""

from functools import lru_cache

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
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # --- Security ---
    secret_key: str = Field(alias="SECRET_KEY")
    session_cookie_name: str = "relay_session"
    session_token_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days

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

    # --- Observability ---
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

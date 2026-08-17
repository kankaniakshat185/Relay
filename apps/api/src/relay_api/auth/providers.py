"""Login OAuth provider configuration — GitHub, Slack, Google.

Minimal identity scopes only. This is intentionally separate from any
provider config under `connectors/`, which requests much broader data-access
scopes for the *same* providers — see plan.md §4.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from relay_api.core.config import get_settings


@dataclass(frozen=True)
class NormalizedIdentity:
    provider_user_id: str
    email: str
    display_name: str
    avatar_url: str | None


@dataclass(frozen=True)
class LoginProvider:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    normalize: Callable[[dict[str, Any]], NormalizedIdentity]
    # Extra headers/params some providers require on the userinfo request.
    userinfo_headers: dict[str, str] | None = None


def _normalize_github(data: dict[str, Any]) -> NormalizedIdentity:
    return NormalizedIdentity(
        provider_user_id=str(data["id"]),
        email=data.get("email") or f"{data['login']}@users.noreply.github.com",
        display_name=data.get("name") or data["login"],
        avatar_url=data.get("avatar_url"),
    )


def _normalize_slack(data: dict[str, Any]) -> NormalizedIdentity:
    identity = data.get("https://slack.com/user_id", data.get("sub"))
    return NormalizedIdentity(
        provider_user_id=str(identity),
        email=data["email"],
        display_name=data.get("name") or data["email"],
        avatar_url=data.get("picture"),
    )


def _normalize_google(data: dict[str, Any]) -> NormalizedIdentity:
    return NormalizedIdentity(
        provider_user_id=str(data["sub"]),
        email=data["email"],
        display_name=data.get("name") or data["email"],
        avatar_url=data.get("picture"),
    )


def get_login_providers() -> dict[str, LoginProvider]:
    settings = get_settings()
    return {
        "github": LoginProvider(
            name="github",
            client_id=settings.github_login_client_id,
            client_secret=settings.github_login_client_secret,
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            scope="read:user user:email",
            normalize=_normalize_github,
            userinfo_headers={"Accept": "application/vnd.github+json"},
        ),
        "slack": LoginProvider(
            name="slack",
            client_id=settings.slack_login_client_id,
            client_secret=settings.slack_login_client_secret,
            authorize_url="https://slack.com/openid/connect/authorize",
            token_url="https://slack.com/api/openid.connect.token",
            userinfo_url="https://slack.com/api/openid.connect.userInfo",
            scope="openid email profile",
            normalize=_normalize_slack,
        ),
        "google": LoginProvider(
            name="google",
            client_id=settings.google_login_client_id,
            client_secret=settings.google_login_client_secret,
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            scope="openid email profile",
            normalize=_normalize_google,
        ),
    }

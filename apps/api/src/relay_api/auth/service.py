"""Login OAuth flow logic: authorize-url building, code exchange, and
find-or-create-user. Kept separate from `router.py` so it's testable
without spinning up HTTP — the router should stay a thin translation layer.
"""

import secrets
import uuid
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import AuthIdentity, User
from relay_api.auth.providers import LoginProvider, NormalizedIdentity
from relay_api.core.config import get_settings


class OAuthExchangeError(Exception):
    """The provider's own token endpoint reported a failure — GitHub's
    classic OAuth token endpoint in particular returns HTTP 200 even on
    failure (`{"error": ..., "error_description": ...}` in the body
    instead of `access_token`), so `raise_for_status()` alone never
    catches it; found live as a raw 500/`KeyError: 'access_token'` with
    the actual reason (a stale client secret, a reused/expired code, a
    redirect_uri mismatch at the exchange step specifically) silently
    discarded. The router turns this into a clean 400, not a 500."""


def build_authorization_url(provider: LoginProvider, redirect_uri: str) -> tuple[str, str]:
    """Returns (authorization_url, state). Caller is responsible for
    persisting `state` (e.g. in a short-lived signed cookie) and verifying
    it on callback to prevent CSRF."""
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "scope": provider.scope,
        "state": state,
        "response_type": "code",
    }
    return f"{provider.authorize_url}?{urlencode(params)}", state


async def exchange_code_for_identity(
    provider: LoginProvider, code: str, redirect_uri: str
) -> NormalizedIdentity:
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            provider.token_url,
            data={
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        if "error" in token_data:
            reason = token_data.get("error_description") or token_data["error"]
            raise OAuthExchangeError(f"{provider.name} token exchange failed: {reason}")
        access_token = token_data["access_token"]

        userinfo_response = await client.get(
            provider.userinfo_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                **(provider.userinfo_headers or {}),
            },
        )
        userinfo_response.raise_for_status()
        return provider.normalize(userinfo_response.json())


async def find_or_create_user(
    db: AsyncSession, provider_name: str, identity: NormalizedIdentity
) -> User:
    existing_identity = await db.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == provider_name,
            AuthIdentity.provider_user_id == identity.provider_user_id,
        )
    )
    if existing_identity is not None:
        user = await db.get(User, existing_identity.user_id)
        assert user is not None
        return user

    # New provider identity — attach to an existing user with the same email
    # if one exists, otherwise create a new account.
    user = await db.scalar(select(User).where(User.email == identity.email))
    if user is None:
        user = User(
            email=identity.email,
            display_name=identity.display_name,
            avatar_url=identity.avatar_url,
        )
        db.add(user)
        await db.flush()

    db.add(
        AuthIdentity(
            user_id=user.id,
            provider=provider_name,
            provider_user_id=identity.provider_user_id,
            provider_email=identity.email,
        )
    )
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


def frontend_redirect_url(path: str = "/") -> str:
    return f"{get_settings().frontend_url}{path}"

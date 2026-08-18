"""CRUD over `connector_credentials`. Shared across all three providers —
this is where "one row per (user, provider)" (see `models.py`) is actually
enforced in code, not just at the DB constraint level."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.connectors.base import ConnectorAccount
from relay_api.connectors.encryption import decrypt_token, encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.connectors.registry import ALL_PROVIDERS, get_refreshable_provider
from relay_api.connectors.schemas import ConnectorStatus

# Refresh a bit before actual expiry, not exactly at it — avoids a race
# where a token that's technically still valid when checked expires by
# the time the outbound API call actually lands.
_REFRESH_BUFFER = timedelta(seconds=60)


class TokenRefreshError(Exception):
    """Raised when a provider's refresh grant itself fails — e.g. the
    refresh token was revoked or already consumed. Reconnecting via the
    Connections page is the only recovery; see docs/phases/1-context-searcher.md."""


async def get_credential(
    db: AsyncSession, user_id: uuid.UUID, provider: str
) -> ConnectorCredential | None:
    credential = await db.scalar(
        select(ConnectorCredential).where(
            ConnectorCredential.user_id == user_id, ConnectorCredential.provider == provider
        )
    )
    return credential


async def upsert_credential(
    db: AsyncSession, user_id: uuid.UUID, provider: str, account: ConnectorAccount
) -> ConnectorCredential:
    credential = await get_credential(db, user_id, provider)
    if credential is None:
        credential = ConnectorCredential(user_id=user_id, provider=provider)
        db.add(credential)

    credential.access_token_encrypted = encrypt_token(account.access_token)
    credential.refresh_token_encrypted = (
        encrypt_token(account.refresh_token) if account.refresh_token else None
    )
    credential.scope = account.scope
    credential.expires_at = account.expires_at
    credential.external_account_id = account.external_account_id
    credential.external_account_label = account.external_account_label

    await db.commit()
    await db.refresh(credential)
    return credential


async def delete_credential(db: AsyncSession, user_id: uuid.UUID, provider: str) -> None:
    credential = await get_credential(db, user_id, provider)
    if credential is not None:
        await db.delete(credential)
        await db.commit()


async def list_statuses(db: AsyncSession, user_id: uuid.UUID) -> list[ConnectorStatus]:
    result = await db.execute(
        select(ConnectorCredential).where(ConnectorCredential.user_id == user_id)
    )
    connected = {c.provider: c for c in result.scalars().all()}

    return [
        ConnectorStatus(
            provider=provider,
            connected=provider in connected,
            external_account_label=(
                connected[provider].external_account_label if provider in connected else None
            ),
            connected_at=connected[provider].created_at if provider in connected else None,
        )
        for provider in ALL_PROVIDERS
    ]


def decrypted_access_token(credential: ConnectorCredential) -> str:
    return decrypt_token(credential.access_token_encrypted)


async def ensure_valid_access_token(db: AsyncSession, credential: ConnectorCredential) -> str:
    """Returns a decrypted access token guaranteed usable right now,
    transparently refreshing — and persisting — it first if it's expired
    or about to be. Providers with non-expiring tokens (`expires_at is
    None`, e.g. GitHub/Slack today) or without a refresh implementation
    pass straight through unchanged: this is the only place a caller
    needs to know refreshing exists at all.

    Raises `TokenRefreshError` if a refresh was needed and the provider's
    refresh grant itself failed (revoked/expired refresh token) — callers
    should treat that as "this connector needs reconnecting", not retry.
    """
    if credential.expires_at is None:
        return decrypted_access_token(credential)

    if datetime.now(UTC) < credential.expires_at - _REFRESH_BUFFER:
        return decrypted_access_token(credential)

    refreshable = get_refreshable_provider(credential.provider)
    if refreshable is None or credential.refresh_token_encrypted is None:
        # Expired with no way to refresh — same behavior as before this
        # existed: hand back the stale token and let the API call fail
        # naturally with a 401 the caller already has to handle.
        return decrypted_access_token(credential)

    try:
        refreshed = await refreshable.refresh_access_token(
            decrypt_token(credential.refresh_token_encrypted)
        )
    except httpx.HTTPStatusError as exc:
        raise TokenRefreshError(
            f"{credential.provider} token refresh failed: {exc.response.status_code}"
        ) from exc

    credential.access_token_encrypted = encrypt_token(refreshed.access_token)
    if refreshed.refresh_token:
        credential.refresh_token_encrypted = encrypt_token(refreshed.refresh_token)
    credential.expires_at = refreshed.expires_at
    await db.commit()
    await db.refresh(credential)

    return refreshed.access_token

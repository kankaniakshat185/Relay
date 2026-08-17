"""CRUD over `connector_credentials`. Shared across all three providers —
this is where "one row per (user, provider)" (see `models.py`) is actually
enforced in code, not just at the DB constraint level."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.connectors.base import ConnectorAccount
from relay_api.connectors.encryption import decrypt_token, encrypt_token
from relay_api.connectors.models import ConnectorCredential
from relay_api.connectors.registry import ALL_PROVIDERS
from relay_api.connectors.schemas import ConnectorStatus


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

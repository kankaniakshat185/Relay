"""`list_all_credentials` — the one query in `connectors/service.py` that
spans every user, not just the requesting one, so it's worth proving
against a real DB with more than one user's rows present."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.models import User
from relay_api.connectors import service as connector_service
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential


async def test_list_all_credentials_spans_every_user(db: AsyncSession, test_user: User) -> None:
    other_user = User(email=f"{uuid.uuid4()}@example.com", display_name="Other User")
    db.add(other_user)
    await db.commit()
    await db.refresh(other_user)

    db.add(
        ConnectorCredential(
            user_id=test_user.id,
            provider="github",
            access_token_encrypted=encrypt_token("tok-a"),
            scope="repo",
            external_account_id="1",
            external_account_label="a",
        )
    )
    db.add(
        ConnectorCredential(
            user_id=other_user.id,
            provider="slack",
            access_token_encrypted=encrypt_token("tok-b"),
            scope="",
            external_account_id="2",
            external_account_label="b",
        )
    )
    await db.commit()

    all_credentials = await connector_service.list_all_credentials(db)

    pairs = {(c.user_id, c.provider) for c in all_credentials}
    assert (test_user.id, "github") in pairs
    assert (other_user.id, "slack") in pairs

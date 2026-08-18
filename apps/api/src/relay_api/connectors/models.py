"""`connector_credentials` — data-access tokens, separate from login
identity (`auth/models.py`). See ADR 0003.

One row per (user, provider) — Phase 1 supports exactly one connected
account per provider per user (one GitHub account, one Slack workspace,
one Jira site). Multiple accounts per provider is a real limitation, not
an oversight — it's out of scope until a feature actually needs it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from relay_api.core.db import Base


class ConnectorCredential(Base):
    __tablename__ = "connector_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_connector_user_provider"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(32))  # "github" | "slack" | "jira"

    # Fernet-encrypted (connectors/encryption.py) — never stored plaintext.
    # Text, not a bounded VARCHAR: GitHub/Slack tokens are short opaque
    # strings, but Jira's OAuth tokens are long (JWT-style) and, once
    # Fernet-encrypted (~33% base64 overhead on top), blow well past any
    # size that looked reasonable for the other two providers. Found by
    # actually connecting Jira, not by guessing a bigger number up front.
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, default=None)

    scope: Mapped[str] = mapped_column(String(512))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Human-readable label for the Connections page, e.g. GitHub login,
    # Slack team name, Jira site URL. Also doubles as the provider-specific
    # id some connectors need for API calls (e.g. Jira's cloud id).
    external_account_label: Mapped[str] = mapped_column(String(255))
    external_account_id: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

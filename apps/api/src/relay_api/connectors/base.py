"""Shared connector OAuth types.

Unlike login (`auth/providers.py`), connector exchange logic isn't
uniform enough to reduce to one generic function + config — Jira needs an
extra "accessible resources" round trip to resolve a cloud id, Slack's
data-access flow is a bot-token install rather than a user token, GitHub is
the "normal" case. Each provider implements `ConnectorProvider` itself;
`connectors/registry.py` is the single place that knows all three exist.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ConnectorAccount:
    """Result of a successful connector OAuth exchange — everything
    `connectors/service.py` needs to persist a `ConnectorCredential` row."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    scope: str
    external_account_id: str
    external_account_label: str


class ConnectorProvider(Protocol):
    name: str

    def authorization_url(self, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorAccount: ...

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


@dataclass(frozen=True)
class RefreshedTokens:
    """Result of successfully refreshing an expired access token — see
    `RefreshableConnectorProvider`. Deliberately not `ConnectorAccount`: a
    refresh never changes which external account is connected, so there's
    no `external_account_id`/`external_account_label` to carry."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None


class RefreshableConnectorProvider(Protocol):
    """A second, optional protocol — not every provider needs it. Slack's
    bot tokens don't expire under the classic install flow, so only
    providers that actually issue short-lived access tokens implement
    this (Jira; GitHub too, if the OAuth App owner has "expire user
    authorization tokens" turned on — found live, see the Phase 2 retro).
    `connectors/registry.get_refreshable_provider` is the single place
    that knows which ones do."""

    async def refresh_access_token(self, refresh_token: str) -> RefreshedTokens: ...


class RefreshGrantError(Exception):
    """Raised by a provider's own `refresh_access_token` when the grant
    itself is rejected. Providers signal this differently at the HTTP
    level — Atlassian uses a real error status (`httpx.HTTPStatusError`
    covers that case directly), GitHub returns 200 with an `error` field
    in the body — so this is the one type `connectors/service.py` needs
    to catch regardless of which provider it's refreshing."""

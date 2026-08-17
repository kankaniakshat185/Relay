"""Jira connector OAuth — Atlassian's OAuth 2.0 (3LO) via auth.atlassian.com,
with an extra round trip classic OAuth doesn't need: a user can have
access to multiple Jira Cloud sites, so after the token exchange we call
`accessible-resources` to find out which sites were actually granted and
resolve the cloud id every subsequent API call needs
(`api.atlassian.com/ex/jira/{cloud_id}/...`).

Phase 1 limitation, documented not accidental: only the first accessible
site is connected — same one-account-per-provider simplification as
`connectors/models.py`.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from relay_api.connectors.base import ConnectorAccount
from relay_api.core.config import get_settings

_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
_ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
_SCOPE = "read:jira-work read:jira-user offline_access"

name = "jira"


def authorization_url(redirect_uri: str, state: str) -> str:
    settings = get_settings()
    params = {
        "audience": "api.atlassian.com",
        "client_id": settings.jira_connector_client_id,
        "scope": _SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> ConnectorAccount:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            _TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "client_id": settings.jira_connector_client_id,
                "client_secret": settings.jira_connector_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        token_response.raise_for_status()
        token_data = token_response.json()

        resources_response = await client.get(
            _ACCESSIBLE_RESOURCES_URL,
            headers={
                "Authorization": f"Bearer {token_data['access_token']}",
                "Accept": "application/json",
            },
        )
        resources_response.raise_for_status()
        resources = resources_response.json()

    if not resources:
        raise ValueError("Jira OAuth succeeded but no accessible Jira sites were granted")

    site = resources[0]
    expires_in = token_data.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None

    return ConnectorAccount(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
        scope=token_data.get("scope", _SCOPE),
        external_account_id=site["id"],  # cloud id — needed for every API call, see client.py
        external_account_label=site["url"],
    )

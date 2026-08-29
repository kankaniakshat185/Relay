"""Slack connector OAuth — a bot-token install flow (`oauth.v2.access`),
structurally different from the login flow's OpenID Connect user-token
flow in `auth/providers.py`. A bot user in the workspace is what lets
Relay read channel history on an ongoing basis, not the connecting user's
own token."""

from urllib.parse import urlencode

import httpx

from relay_api.connectors.base import ConnectorAccount, ConnectorExchangeError
from relay_api.core.config import get_settings

_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
_SCOPE = "channels:history channels:read groups:history groups:read users:read"

name = "slack"


def authorization_url(redirect_uri: str, state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.slack_connector_client_id,
        "scope": _SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> ConnectorAccount:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.slack_connector_client_id,
                "client_secret": settings.slack_connector_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

    if not data.get("ok"):
        raise ConnectorExchangeError(f"Slack OAuth error: {data.get('error')}")

    return ConnectorAccount(
        access_token=data["access_token"],
        refresh_token=None,  # bot tokens don't expire under the classic install flow
        expires_at=None,
        scope=data.get("scope", _SCOPE),
        external_account_id=data["team"]["id"],
        external_account_label=data["team"]["name"],
    )

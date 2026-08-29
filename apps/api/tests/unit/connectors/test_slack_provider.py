"""`exchange_code` — Slack's `oauth.v2.access` returns HTTP 200 even on a
rejected exchange (`{"ok": false, "error": ...}`), same shape as GitHub's
classic token endpoint, so this is the one thing worth testing in
isolation here: that a rejected exchange raises `ConnectorExchangeError`,
not a bare `ValueError` with no registered handler (found live)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from relay_api.connectors.base import ConnectorExchangeError
from relay_api.connectors.slack import provider


def _mock_client(response: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


def _oauth_response(body: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", provider._TOKEN_URL)
    return httpx.Response(status_code, json=body, request=request)


async def test_exchange_returns_bot_token_and_workspace_identity() -> None:
    response = _oauth_response(
        {
            "ok": True,
            "access_token": "xoxb-bot-token",
            "scope": "channels:history,channels:read",
            "team": {"id": "T123", "name": "Acme Workspace"},
        }
    )
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.exchange_code("some-code", "https://example.com/callback")

    assert result.access_token == "xoxb-bot-token"
    assert result.refresh_token is None  # classic bot install tokens don't expire
    assert result.expires_at is None
    assert result.external_account_id == "T123"
    assert result.external_account_label == "Acme Workspace"


async def test_exchange_with_ok_false_raises_connector_exchange_error() -> None:
    # Slack signals a rejected exchange with HTTP 200 + `ok: false`, never
    # an error status — `raise_for_status()` never fires here either.
    response = _oauth_response({"ok": False, "error": "bad_redirect_uri"})
    with (
        patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)),
        pytest.raises(ConnectorExchangeError, match="bad_redirect_uri"),
    ):
        await provider.exchange_code("some-code", "https://example.com/callback")

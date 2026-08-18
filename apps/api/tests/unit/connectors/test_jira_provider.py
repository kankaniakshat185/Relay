"""`refresh_access_token` is the piece `connectors/service.ensure_valid_access_token`
depends on — exercised here in isolation against a mocked httpx client, the
same way exchange_code would be if it had a test yet."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from relay_api.connectors.jira import provider


def _mock_client(response: httpx.Response) -> MagicMock:
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


def _token_response(body: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", provider._TOKEN_URL)
    return httpx.Response(status_code, json=body, request=request)


async def test_refresh_returns_new_access_and_rotated_refresh_token() -> None:
    response = _token_response(
        {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    )
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert result.expires_at is not None
    assert result.expires_at > datetime.now(UTC)


async def test_refresh_falls_back_to_input_refresh_token_if_response_omits_one() -> None:
    response = _token_response({"access_token": "new-access", "expires_in": 3600})
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.refresh_token == "old-refresh"


async def test_refresh_with_no_expiry_in_response_leaves_expires_at_none() -> None:
    response = _token_response({"access_token": "new-access", "refresh_token": "new-refresh"})
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.expires_at is None


async def test_refresh_propagates_http_errors_for_the_caller_to_handle() -> None:
    response = _token_response({"error": "invalid_grant"}, status_code=400)
    with (
        patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await provider.refresh_access_token("revoked-refresh")

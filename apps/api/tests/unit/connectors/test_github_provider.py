"""`refresh_access_token` — GitHub's token endpoint signals a rejected
refresh with a 200 + `error` field, not an HTTP error status, unlike
Atlassian's — that's the one thing worth testing in isolation here."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from relay_api.connectors.base import RefreshGrantError
from relay_api.connectors.github import provider


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
        {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 28800}
    )
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert result.expires_at is not None
    assert result.expires_at > datetime.now(UTC)


async def test_refresh_falls_back_to_input_refresh_token_if_response_omits_one() -> None:
    response = _token_response({"access_token": "new-access", "expires_in": 28800})
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.refresh_token == "old-refresh"


async def test_refresh_with_no_expiry_in_response_leaves_expires_at_none() -> None:
    response = _token_response({"access_token": "new-access", "refresh_token": "new-refresh"})
    with patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)):
        result = await provider.refresh_access_token("old-refresh")

    assert result.expires_at is None


async def test_refresh_with_error_body_raises_refresh_grant_error_not_http_error() -> None:
    # GitHub returns 200 OK with an `error` field for a rejected refresh —
    # `raise_for_status()` would never fire, so this has to be checked
    # explicitly in the response body.
    response = _token_response({"error": "bad_refresh_token"}, status_code=200)
    with (
        patch.object(provider.httpx, "AsyncClient", return_value=_mock_client(response)),
        pytest.raises(RefreshGrantError),
    ):
        await provider.refresh_access_token("revoked-refresh")

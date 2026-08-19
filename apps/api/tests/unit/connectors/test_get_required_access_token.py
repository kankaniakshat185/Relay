import uuid
from unittest.mock import AsyncMock

import pytest

from relay_api.connectors import service
from relay_api.connectors.encryption import encrypt_token
from relay_api.connectors.models import ConnectorCredential


async def test_returns_a_valid_token_when_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    credential = ConnectorCredential(
        provider="github",
        access_token_encrypted=encrypt_token("gh-token"),
        scope="repo",
        external_account_id="1",
        external_account_label="octocat",
    )
    monkeypatch.setattr(service, "get_credential", AsyncMock(return_value=credential))

    token = await service.get_required_access_token(object(), uuid.uuid4(), "github")

    assert token == "gh-token"


async def test_raises_connector_not_connected_when_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_credential", AsyncMock(return_value=None))

    with pytest.raises(service.ConnectorNotConnectedError) as exc_info:
        await service.get_required_access_token(object(), uuid.uuid4(), "github")

    assert exc_info.value.provider == "github"

"""GitHub connector OAuth — data-access scopes, separate from
`auth/providers.py`'s GitHub login config (ADR 0003). Read-only in
practice (see `client.py`), even though GitHub's `repo` scope itself grants
more than that — there is no narrower classic-OAuth scope for private-repo
read access. Worth a GitHub App with fine-grained read-only permissions if
this ever needs tightening.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from relay_api.connectors.base import ConnectorAccount
from relay_api.core.config import get_settings

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_SCOPE = "repo read:org read:user"

name = "github"


def authorization_url(redirect_uri: str, state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.github_connector_client_id,
        "redirect_uri": redirect_uri,
        "scope": _SCOPE,
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> ConnectorAccount:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            _TOKEN_URL,
            data={
                "client_id": settings.github_connector_client_id,
                "client_secret": settings.github_connector_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        if "error" in token_data:
            raise ValueError(f"GitHub OAuth error: {token_data['error']}")

        user_response = await client.get(
            _USER_URL,
            headers={
                "Authorization": f"Bearer {token_data['access_token']}",
                "Accept": "application/vnd.github+json",
            },
        )
        user_response.raise_for_status()
        user = user_response.json()

    expires_in = token_data.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in else None

    return ConnectorAccount(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
        scope=token_data.get("scope", _SCOPE),
        external_account_id=str(user["id"]),
        external_account_label=user["login"],
    )

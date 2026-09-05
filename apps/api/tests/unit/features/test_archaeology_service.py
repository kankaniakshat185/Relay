"""`features/archaeology/service.py` is now a thin wrapper: resolve the
GitHub access token, delegate to `engine.timeline.build_timeline`. The
actual collapsing/correlation logic has its own tests at
`tests/unit/engine/test_timeline_service.py`, alongside the code that
moved there — this file only checks the delegation itself."""

import uuid
from unittest.mock import AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.timeline.schemas import TimelineResult
from relay_api.features.archaeology import service

_USER = User(id=uuid.uuid4(), email="dev@example.com", display_name="Dev")


async def test_trace_resolves_the_github_token_and_delegates_to_the_engine() -> None:
    db = object()
    expected = TimelineResult(timeline=[])

    with (
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="a-real-token"),
        ) as mock_token,
        patch.object(
            service.timeline_service, "build_timeline", new=AsyncMock(return_value=expected)
        ) as mock_build,
    ):
        result = await service.trace(
            db,
            _USER,
            owner="acme",
            repo="widgets",
            ref="main",
            path="src/x.py",
            target_type="directory",
        )

    assert result is expected
    mock_token.assert_awaited_once_with(db, _USER.id, "github")
    mock_build.assert_awaited_once_with(
        db,
        _USER.id,
        access_token="a-real-token",
        owner="acme",
        repo="widgets",
        ref="main",
        path="src/x.py",
        target_type="directory",
    )

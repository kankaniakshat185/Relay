import uuid
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.engine.synthesis import service as synthesis_service
from relay_api.engine.synthesis.providers import SynthesisError
from relay_api.engine.timeline.schemas import TimelineEntry, TimelineResult
from relay_api.features.incident_correlation import service

_INCIDENT_AT = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def _make_item(**overrides: object) -> IngestedItem:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "source": "github",
        "source_type": "pull_request",
        "title": "Fix retry logic",
        "body": "Closes a race condition.",
        "url": "https://github.com/acme/widgets/pull/7",
        "author": "octocat",
        "occurred_at": _INCIDENT_AT,
    }
    defaults.update(overrides)
    return IngestedItem(**defaults)  # type: ignore[arg-type]


def _timeline_entry(sha: str, committed_at: datetime) -> TimelineEntry:
    return TimelineEntry(
        sha=sha,
        short_sha=sha[:7],
        message="a commit",
        author="octocat",
        committed_at=committed_at,
        url=f"https://github.com/acme/widgets/commit/{sha}",
        line_ranges=[],
        files_touched=["x.py"],
        pull_request=None,
        jira_ticket_key=None,
        jira_ticket_url=None,
        related_slack=[],
        similar_issues=[],
        review_comments=[],
    )


def _user() -> User:
    return User(id=uuid.uuid4(), email="a@b.com", display_name="A")


async def test_raw_mode_never_calls_a_provider_and_returns_all_ingested_items() -> None:
    items = [_make_item(title="Item zero")]

    with (
        patch.object(service, "get_items_since", new=AsyncMock(return_value=items)),
        patch.dict(synthesis_service.SYNTHESIS_PROVIDERS, {"openai": AsyncMock()}),
    ):
        result = await service.correlate(db=object(), user=_user(), incident_at=_INCIDENT_AT)  # type: ignore[arg-type]

        synthesis_service.SYNTHESIS_PROVIDERS["openai"].assert_not_called()  # type: ignore[attr-defined]

    assert result.used_llm is False
    assert result.narrative is None
    assert len(result.sources) == 1
    assert result.file_trace == []


async def test_window_bounds_are_derived_from_incident_at_and_the_hour_params() -> None:
    fake_get_items_since = AsyncMock(return_value=[])

    with patch.object(service, "get_items_since", new=fake_get_items_since):
        await service.correlate(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            incident_at=_INCIDENT_AT,
            window_before_hours=10,
            window_after_hours=3,
        )

    fake_get_items_since.assert_awaited_once()
    _, kwargs = fake_get_items_since.call_args
    assert kwargs["since"] == datetime(2026, 1, 15, 2, 0, tzinfo=UTC)
    assert kwargs["until"] == datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


async def test_llm_mode_with_byok_key_dispatches_to_provider() -> None:
    items = [_make_item(title="Item zero"), _make_item(title="Item one")]
    fake_synthesize = AsyncMock(return_value=("Likely caused by item one.", [1]))

    with (
        patch.object(service, "get_items_since", new=AsyncMock(return_value=items)),
        patch.object(synthesis_service, "check_and_increment_daily", new=AsyncMock()) as mock_rl,
        patch.dict(synthesis_service.SYNTHESIS_PROVIDERS, {"anthropic": fake_synthesize}),
    ):
        result = await service.correlate(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            incident_at=_INCIDENT_AT,
            use_llm=True,
            llm_provider="anthropic",
            byok_api_key="sk-ant-user-supplied-key",
        )

        mock_rl.assert_not_called()

    assert result.used_llm is True
    assert result.narrative == "Likely caused by item one."
    assert len(result.sources) == 1
    assert result.sources[0].title == "Item one"


async def test_invalid_byok_key_surfaces_as_a_clean_reason_not_a_500() -> None:
    items = [_make_item()]
    failing_synthesize = AsyncMock(side_effect=SynthesisError("invalid_api_key", "401"))

    with (
        patch.object(service, "get_items_since", new=AsyncMock(return_value=items)),
        patch.dict(synthesis_service.SYNTHESIS_PROVIDERS, {"openai": failing_synthesize}),
    ):
        result = await service.correlate(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            incident_at=_INCIDENT_AT,
            use_llm=True,
            byok_api_key="sk-a-bad-key",
        )

    assert result.used_llm is False
    assert result.llm_unavailable_reason == "invalid_api_key"
    assert len(result.sources) == 1  # raw results still returned, not lost


async def test_no_file_path_skips_the_timeline_lookup_entirely() -> None:
    with (
        patch.object(service, "get_items_since", new=AsyncMock(return_value=[])),
        patch.object(service.timeline_service, "build_timeline", new=AsyncMock()) as mock_build,
    ):
        result = await service.correlate(db=object(), user=_user(), incident_at=_INCIDENT_AT)  # type: ignore[arg-type]

    mock_build.assert_not_awaited()
    assert result.file_trace == []


async def test_file_path_traces_the_file_and_filters_commits_to_the_incident_window() -> None:
    in_window = _timeline_entry("in-window", datetime(2026, 1, 15, 6, 0, tzinfo=UTC))
    outside_window = _timeline_entry("too-old", datetime(2025, 1, 1, tzinfo=UTC))
    timeline_result = TimelineResult(timeline=[in_window, outside_window])

    with (
        patch.object(service, "get_items_since", new=AsyncMock(return_value=[])),
        patch.object(
            service.connector_service,
            "get_required_access_token",
            new=AsyncMock(return_value="tok"),
        ),
        patch.object(
            service.timeline_service, "build_timeline", new=AsyncMock(return_value=timeline_result)
        ) as mock_build,
    ):
        result = await service.correlate(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            incident_at=_INCIDENT_AT,
            owner="acme",
            repo="widgets",
            ref="main",
            file_path="src/x.py",
        )

    mock_build.assert_awaited_once_with(
        ANY, ANY, access_token="tok", owner="acme", repo="widgets", ref="main", path="src/x.py"
    )
    assert [e.sha for e in result.file_trace] == ["in-window"]

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.features.context_search import service
from relay_api.features.context_search.llm_providers import SynthesisError


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
        "occurred_at": datetime(2026, 1, 15, tzinfo=UTC),
    }
    defaults.update(overrides)
    return IngestedItem(**defaults)  # type: ignore[arg-type]


def _user() -> User:
    return User(id=uuid.uuid4(), email="a@b.com", display_name="A")


async def test_raw_mode_never_calls_a_provider_and_returns_no_answer() -> None:
    items = [_make_item(title="Item zero")]

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.dict(service.SYNTHESIS_PROVIDERS, {"openai": AsyncMock()}),
    ):
        result = await service.search(db=object(), user=_user(), query="anything")  # type: ignore[arg-type]

        service.SYNTHESIS_PROVIDERS["openai"].assert_not_called()  # type: ignore[attr-defined]

    assert result.used_llm is False
    assert result.answer is None
    assert len(result.sources) == 1
    assert result.sources[0].excerpt  # populated even without an LLM


async def test_raw_mode_with_no_indexed_items_returns_empty_sources() -> None:
    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])):
        result = await service.search(db=object(), user=_user(), query="anything")  # type: ignore[arg-type]

    assert result.used_llm is False
    assert result.sources == []


async def test_llm_mode_with_byok_key_skips_rate_limit_and_dispatches_to_provider() -> None:
    items = [_make_item(title="Item zero"), _make_item(title="Item one")]
    fake_synthesize = AsyncMock(return_value=("It's item one.", [1]))

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.object(service, "check_and_increment_daily", new=AsyncMock()) as mock_rate_limit,
        patch.dict(service.SYNTHESIS_PROVIDERS, {"anthropic": fake_synthesize}),
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="which one?",
            use_llm=True,
            llm_provider="anthropic",
            byok_api_key="sk-ant-user-supplied-key",
        )

        mock_rate_limit.assert_not_called()
        fake_synthesize.assert_called_once()
        assert fake_synthesize.call_args.args[2] == "sk-ant-user-supplied-key"

    assert result.used_llm is True
    assert result.answer == "It's item one."
    assert len(result.sources) == 1
    assert result.sources[0].title == "Item one"


async def test_llm_mode_falls_back_to_all_items_when_no_indices_cited() -> None:
    items = [_make_item(title="Item zero"), _make_item(title="Item one")]
    fake_synthesize = AsyncMock(return_value=("Unclear.", []))

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.object(service, "check_and_increment_daily", new=AsyncMock(return_value=True)),
        patch.dict(service.SYNTHESIS_PROVIDERS, {"openai": fake_synthesize}),
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="which one?",
            use_llm=True,
        )

    assert len(result.sources) == 2


async def test_free_tier_without_byok_key_hitting_rate_limit_falls_back_to_raw() -> None:
    items = [_make_item(title="Item zero")]
    fake_synthesize = AsyncMock()

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.object(service, "check_and_increment_daily", new=AsyncMock(return_value=False)),
        patch.dict(service.SYNTHESIS_PROVIDERS, {"openai": fake_synthesize}),
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="anything",
            use_llm=True,
        )

        fake_synthesize.assert_not_called()

    assert result.used_llm is False
    assert result.llm_unavailable_reason == "rate_limited"
    assert result.answer is None
    assert len(result.sources) == 1  # raw results still returned, not lost


async def test_invalid_byok_key_surfaces_as_a_clean_reason_not_a_500() -> None:
    items = [_make_item(title="Item zero")]
    failing_synthesize = AsyncMock(
        side_effect=SynthesisError("invalid_api_key", "401 invalid api key")
    )

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.dict(service.SYNTHESIS_PROVIDERS, {"openai": failing_synthesize}),
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="anything",
            use_llm=True,
            byok_api_key="sk-a-bad-key",
        )

    assert result.used_llm is False
    assert result.llm_unavailable_reason == "invalid_api_key"
    assert result.answer is None
    assert len(result.sources) == 1  # raw results still returned, not lost


async def test_transient_provider_failure_surfaces_as_provider_error_not_a_500() -> None:
    items = [_make_item(title="Item zero")]
    failing_synthesize = AsyncMock(
        side_effect=SynthesisError("provider_error", "503 upstream unavailable")
    )

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.dict(service.SYNTHESIS_PROVIDERS, {"openai": failing_synthesize}),
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="anything",
            use_llm=True,
            byok_api_key="sk-a-fine-key",
        )

    assert result.used_llm is False
    assert result.llm_unavailable_reason == "provider_error"
    assert len(result.sources) == 1


async def test_non_openai_provider_without_byok_key_requires_a_key_not_free_tier() -> None:
    """There is no free tier for Groq/Anthropic/Gemini — only OpenAI, since
    that's the only key Relay itself pays for (ADR 0008)."""
    items = [_make_item(title="Item zero")]

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch.object(service, "check_and_increment_daily", new=AsyncMock()) as mock_rate_limit,
    ):
        result = await service.search(
            db=object(),  # type: ignore[arg-type]
            user=_user(),
            query="anything",
            use_llm=True,
            llm_provider="groq",
        )

        mock_rate_limit.assert_not_called()

    assert result.used_llm is False
    assert result.llm_unavailable_reason == "api_key_required"
    assert len(result.sources) == 1

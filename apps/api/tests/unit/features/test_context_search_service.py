import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from relay_api.auth.models import User
from relay_api.engine.ingestion.models import IngestedItem
from relay_api.features.context_search import service


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


async def test_returns_placeholder_answer_when_nothing_indexed() -> None:
    user = User(id=uuid.uuid4(), email="a@b.com", display_name="A")

    with patch.object(service, "engine_search", new=AsyncMock(return_value=[])):
        result = await service.search(db=object(), user=user, query="anything")  # type: ignore[arg-type]

    assert result.sources == []
    assert "connect" in result.answer.lower()


async def test_maps_cited_indices_back_to_source_items() -> None:
    user = User(id=uuid.uuid4(), email="a@b.com", display_name="A")
    items = [_make_item(title="Item zero"), _make_item(title="Item one")]

    fake_completion_content = json.dumps({"answer": "It's item one.", "cited_indices": [1]})
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content=fake_completion_content))]

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch("relay_api.features.context_search.service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        result = await service.search(db=object(), user=user, query="which one?")  # type: ignore[arg-type]

    assert result.answer == "It's item one."
    assert len(result.sources) == 1
    assert result.sources[0].title == "Item one"


async def test_falls_back_to_all_items_when_no_indices_cited() -> None:
    user = User(id=uuid.uuid4(), email="a@b.com", display_name="A")
    items = [_make_item(title="Item zero"), _make_item(title="Item one")]

    fake_completion_content = json.dumps({"answer": "Unclear.", "cited_indices": []})
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content=fake_completion_content))]

    with (
        patch.object(service, "engine_search", new=AsyncMock(return_value=items)),
        patch("relay_api.features.context_search.service.AsyncOpenAI") as mock_openai_cls,
    ):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

        result = await service.search(db=object(), user=user, query="which one?")  # type: ignore[arg-type]

    assert len(result.sources) == 2

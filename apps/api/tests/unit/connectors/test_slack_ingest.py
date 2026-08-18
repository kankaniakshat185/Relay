"""Found live: a bot invited to some but not all channels made the whole
indexing run fail on the first inaccessible channel, losing every channel
that would have worked fine — `conversations.list` returns channels the
bot can *see*, not channels it's actually a *member* of."""

from unittest.mock import AsyncMock, patch

from relay_api.connectors.slack import ingest


async def test_one_unreadable_channel_does_not_block_the_others() -> None:
    channels = [
        {"id": "C1", "name": "no-access"},
        {"id": "C2", "name": "eng-alerts"},
    ]
    messages_by_channel = {
        "C2": [{"text": "the payment webhook is retrying too much", "user": "U1", "ts": "1.0"}],
    }

    async def fake_list_recent_messages(_token: str, channel_id: str, limit: int) -> list[dict]:
        if channel_id == "C1":
            raise RuntimeError("Slack API error (conversations.history): not_in_channel")
        return messages_by_channel.get(channel_id, [])

    with (
        patch.object(ingest.client, "list_channels", new=AsyncMock(return_value=channels)),
        patch.object(ingest.client, "list_recent_messages", side_effect=fake_list_recent_messages),
    ):
        items = await ingest.fetch_normalized_items("token", team_id="T1")

    assert len(items) == 1
    assert items[0].extra["channel"] == "eng-alerts"

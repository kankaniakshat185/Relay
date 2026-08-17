from relay_api.connectors.slack import client, normalize
from relay_api.engine.ingestion.schemas import NormalizedItem

_CHANNEL_LIMIT = 10
_MESSAGE_LIMIT_PER_CHANNEL = 50


async def fetch_normalized_items(access_token: str, team_id: str) -> list[NormalizedItem]:
    channels = await client.list_channels(access_token, limit=_CHANNEL_LIMIT)

    items: list[NormalizedItem] = []
    for channel in channels:
        messages = await client.list_recent_messages(
            access_token, channel["id"], limit=_MESSAGE_LIMIT_PER_CHANNEL
        )
        for message in messages:
            normalized = normalize.normalize_message(
                message, channel["id"], channel["name"], team_id
            )
            if normalized is not None:
                items.append(normalized)

    return items

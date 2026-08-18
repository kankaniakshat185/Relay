from relay_api.connectors.slack import client, normalize
from relay_api.core.logging import get_logger
from relay_api.engine.ingestion.schemas import NormalizedItem

logger = get_logger(__name__)

_CHANNEL_LIMIT = 10
_MESSAGE_LIMIT_PER_CHANNEL = 50


async def fetch_normalized_items(access_token: str, team_id: str) -> list[NormalizedItem]:
    channels = await client.list_channels(access_token, limit=_CHANNEL_LIMIT)

    items: list[NormalizedItem] = []
    for channel in channels:
        # `conversations.list` returns channels the bot can *see* (public
        # ones especially), which isn't the same as being a *member* of
        # them — `conversations.history` only works for the latter. Found
        # live: a bot invited to some but not all channels made the whole
        # indexing run fail on the first inaccessible one, losing every
        # channel that would have worked. One bad channel shouldn't cost
        # the others.
        try:
            messages = await client.list_recent_messages(
                access_token, channel["id"], limit=_MESSAGE_LIMIT_PER_CHANNEL
            )
        except RuntimeError as exc:
            logger.warning(
                "slack_channel_unreadable",
                extra={
                    "channel": channel.get("name"),
                    "channel_id": channel["id"],
                    "error": str(exc),
                },
            )
            continue

        for message in messages:
            normalized = normalize.normalize_message(
                message, channel["id"], channel["name"], team_id
            )
            if normalized is not None:
                items.append(normalized)

    return items

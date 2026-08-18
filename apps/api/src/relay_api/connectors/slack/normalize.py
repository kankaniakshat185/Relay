from datetime import UTC, datetime
from typing import Any

from relay_api.connectors.text_utils import truncate_title
from relay_api.engine.ingestion.schemas import NormalizedItem

_SKIPPED_SUBTYPES = {"channel_join", "channel_leave", "channel_topic", "channel_purpose"}


def normalize_message(
    message: dict[str, Any], channel_id: str, channel_name: str, team_id: str
) -> NormalizedItem | None:
    text = (message.get("text") or "").strip()
    if not text or message.get("subtype") in _SKIPPED_SUBTYPES:
        return None

    ts = message["ts"]
    return NormalizedItem(
        source="slack",
        source_type="message",
        external_id=f"{channel_id}:{ts}",
        title=truncate_title(text),
        body=text,
        url=f"https://app.slack.com/client/{team_id}/{channel_id}/thread/{channel_id}-{ts}",
        author=message.get("user"),
        occurred_at=datetime.fromtimestamp(float(ts), tz=UTC),
        extra={"channel": channel_name, "channel_id": channel_id},
    )

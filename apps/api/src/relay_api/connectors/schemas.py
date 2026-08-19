from datetime import datetime

from pydantic import BaseModel


class ConnectorStatus(BaseModel):
    provider: str
    connected: bool
    external_account_label: str | None = None
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    """When the periodic or manually-triggered sync last completed for
    this connector — `None` if never (still queued from initial connect,
    or the very first sync hasn't finished yet)."""

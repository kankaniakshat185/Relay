from datetime import datetime

from pydantic import BaseModel


class ConnectorStatus(BaseModel):
    provider: str
    connected: bool
    external_account_label: str | None = None
    connected_at: datetime | None = None

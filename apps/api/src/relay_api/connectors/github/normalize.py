from datetime import datetime
from typing import Any

from relay_api.engine.ingestion.schemas import NormalizedItem


def normalize_pull_request(pr: dict[str, Any], repo_full_name: str) -> NormalizedItem:
    return NormalizedItem(
        source="github",
        source_type="pull_request",
        external_id=str(pr["id"]),
        title=pr["title"],
        body=pr.get("body") or "",
        url=pr["html_url"],
        author=(pr.get("user") or {}).get("login"),
        occurred_at=datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00")),
        extra={"repo": repo_full_name, "state": pr["state"], "number": pr["number"]},
    )

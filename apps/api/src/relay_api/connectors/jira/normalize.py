from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from relay_api.engine.ingestion.schemas import NormalizedItem


def _adf_to_text(node: Any) -> str:
    """Flattens Jira's Atlassian Document Format (a nested JSON tree) into
    plain text — descriptions aren't a plain string field in the v3 API."""
    parts: list[str] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if n.get("type") == "text":
                parts.append(n.get("text", ""))
            for child in n.get("content") or []:
                walk(child)
        elif isinstance(n, list):
            for child in n:
                walk(child)

    walk(node)
    return " ".join(parts)


def normalize_issue(issue: dict[str, Any], site_url: str) -> NormalizedItem:
    fields = issue["fields"]
    status = fields.get("status") or {}
    issue_type = fields.get("issuetype") or {}
    assignee = fields.get("assignee") or {}

    occurred_at: datetime = date_parser.isoparse(fields["updated"])

    return NormalizedItem(
        source="jira",
        source_type="issue",
        external_id=issue["id"],
        title=fields["summary"],
        body=_adf_to_text(fields.get("description")),
        url=f"{site_url}/browse/{issue['key']}",
        author=assignee.get("displayName"),
        occurred_at=occurred_at,
        extra={
            "key": issue["key"],
            "status": status.get("name"),
            "issue_type": issue_type.get("name"),
        },
    )

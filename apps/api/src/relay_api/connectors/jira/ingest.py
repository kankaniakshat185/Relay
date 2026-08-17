from relay_api.connectors.jira import client, normalize
from relay_api.engine.ingestion.schemas import NormalizedItem

_ISSUE_LIMIT = 50


async def fetch_normalized_items(
    access_token: str, cloud_id: str, site_url: str
) -> list[NormalizedItem]:
    issues = await client.list_recent_issues(access_token, cloud_id, limit=_ISSUE_LIMIT)
    return [normalize.normalize_issue(issue, site_url) for issue in issues]

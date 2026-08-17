from relay_api.connectors.jira.normalize import normalize_issue


def test_normalizes_an_issue_with_adf_description() -> None:
    issue = {
        "id": "10001",
        "key": "REL-1",
        "fields": {
            "summary": "Investigate flaky auth test",
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Fails intermittently on "},
                            {"type": "text", "text": "CI only."},
                        ],
                    }
                ],
            },
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "assignee": {"displayName": "Priya Patel"},
            "updated": "2026-01-15T10:30:00.000+0000",
        },
    }

    item = normalize_issue(issue, site_url="https://acme.atlassian.net")

    assert item.source == "jira"
    assert item.source_type == "issue"
    assert item.external_id == "10001"
    assert item.title == "Investigate flaky auth test"
    assert item.body == "Fails intermittently on  CI only."
    assert item.url == "https://acme.atlassian.net/browse/REL-1"
    assert item.author == "Priya Patel"
    assert item.extra == {"key": "REL-1", "status": "In Progress", "issue_type": "Bug"}


def test_handles_missing_description_and_assignee() -> None:
    issue = {
        "id": "10002",
        "key": "REL-2",
        "fields": {
            "summary": "Unassigned ticket",
            "description": None,
            "status": {"name": "To Do"},
            "issuetype": {"name": "Task"},
            "assignee": None,
            "updated": "2026-01-01T00:00:00.000+0000",
        },
    }

    item = normalize_issue(issue, site_url="https://acme.atlassian.net")

    assert item.body == ""
    assert item.author is None

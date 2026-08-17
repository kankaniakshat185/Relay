from datetime import UTC, datetime

from relay_api.connectors.github.normalize import normalize_pull_request


def test_normalizes_a_pull_request() -> None:
    pr = {
        "id": 42,
        "number": 7,
        "title": "Fix retry logic",
        "body": "Closes a race condition in the retry loop.",
        "html_url": "https://github.com/acme/widgets/pull/7",
        "state": "open",
        "user": {"login": "octocat"},
        "updated_at": "2026-01-15T10:30:00Z",
    }

    item = normalize_pull_request(pr, repo_full_name="acme/widgets")

    assert item.source == "github"
    assert item.source_type == "pull_request"
    assert item.external_id == "42"
    assert item.title == "Fix retry logic"
    assert item.author == "octocat"
    assert item.url == "https://github.com/acme/widgets/pull/7"
    assert item.occurred_at == datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    assert item.extra == {"repo": "acme/widgets", "state": "open", "number": 7}


def test_handles_missing_body_and_missing_user() -> None:
    pr = {
        "id": 1,
        "number": 1,
        "title": "No description PR",
        "body": None,
        "html_url": "https://github.com/acme/widgets/pull/1",
        "state": "closed",
        "user": None,
        "updated_at": "2026-01-01T00:00:00Z",
    }

    item = normalize_pull_request(pr, repo_full_name="acme/widgets")

    assert item.body == ""
    assert item.author is None

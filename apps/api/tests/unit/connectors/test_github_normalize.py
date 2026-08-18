from datetime import UTC, datetime

from relay_api.connectors.github.normalize import normalize_commit, normalize_pull_request


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


def test_normalizes_a_commit() -> None:
    commit = {
        "sha": "abc1234def5678900112233445566778899aabb",
        "html_url": "https://github.com/acme/widgets/commit/abc1234",
        "commit": {
            "message": "Fix retry logic\n\nCloses a race condition in the retry loop.",
            "author": {"name": "Octo Cat", "date": "2026-01-15T10:30:00Z"},
        },
        "author": {"login": "octocat"},
    }

    item = normalize_commit(commit, repo_full_name="acme/widgets")

    assert item.source == "github"
    assert item.source_type == "commit"
    assert item.external_id == "abc1234def5678900112233445566778899aabb"
    assert item.title == "Fix retry logic"
    assert item.body == "Fix retry logic\n\nCloses a race condition in the retry loop."
    assert item.author == "octocat"
    assert item.url == "https://github.com/acme/widgets/commit/abc1234"
    assert item.occurred_at == datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    assert item.extra == {"repo": "acme/widgets", "sha": "abc1234"}


def test_commit_falls_back_to_git_author_name_when_unlinked_to_a_github_account() -> None:
    commit = {
        "sha": "def456",
        "html_url": "https://github.com/acme/widgets/commit/def456",
        "commit": {
            "message": "Quick fix",
            "author": {"name": "Someone Else", "date": "2026-01-01T00:00:00Z"},
        },
        "author": None,
    }

    item = normalize_commit(commit, repo_full_name="acme/widgets")

    assert item.author == "Someone Else"


def test_commit_with_empty_message_gets_a_placeholder_title() -> None:
    commit = {
        "sha": "ghi789",
        "html_url": "https://github.com/acme/widgets/commit/ghi789",
        "commit": {"message": "", "author": {"name": "Octo Cat", "date": "2026-01-01T00:00:00Z"}},
        "author": {"login": "octocat"},
    }

    item = normalize_commit(commit, repo_full_name="acme/widgets")

    assert item.title == "(no commit message)"

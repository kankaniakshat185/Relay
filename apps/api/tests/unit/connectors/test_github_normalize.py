from datetime import UTC, datetime

from relay_api.connectors.github.normalize import (
    normalize_commit,
    normalize_pull_request,
    normalize_review,
    normalize_review_comment,
)


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


def test_commit_with_a_long_single_line_message_gets_a_truncated_title() -> None:
    """Real bug, real commit: a message with no line breaks means
    `splitlines()[0]` returns the *entire* message — this used to blow
    past `ingested_items.title`'s column limit outright."""
    long_message = "feat: " + ("a very long commit message with no newlines at all " * 20)
    commit = {
        "sha": "jkl012",
        "html_url": "https://github.com/acme/widgets/commit/jkl012",
        "commit": {
            "message": long_message,
            "author": {"name": "Octo Cat", "date": "2026-01-01T00:00:00Z"},
        },
        "author": {"login": "octocat"},
    }

    item = normalize_commit(commit, repo_full_name="acme/widgets")

    assert len(item.title) <= 201  # 200 chars + the ellipsis marker
    assert item.title.startswith("feat:")
    assert item.body == long_message  # full message preserved in body, only title is capped


def test_normalizes_a_review_with_a_body() -> None:
    review = {
        "id": 80,
        "user": {"login": "octocat"},
        "body": "Looks good, one small nit inline.",
        "state": "APPROVED",
        "html_url": "https://github.com/acme/widgets/pull/7#pullrequestreview-80",
        "submitted_at": "2026-01-15T10:30:00Z",
    }

    item = normalize_review(review, repo_full_name="acme/widgets", pr_number=7)

    assert item is not None
    assert item.source == "github"
    assert item.source_type == "review_comment"
    assert item.external_id == "review-80"
    assert item.body == "Looks good, one small nit inline."
    assert item.author == "octocat"
    assert item.url == "https://github.com/acme/widgets/pull/7#pullrequestreview-80"
    assert item.occurred_at == datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
    assert item.extra == {
        "repo": "acme/widgets",
        "pr_number": 7,
        "kind": "review",
        "state": "APPROVED",
    }


def test_review_with_an_empty_body_is_skipped() -> None:
    # A bare "Approve" click with no comment — nothing worth indexing.
    review = {
        "id": 81,
        "user": {"login": "octocat"},
        "body": "",
        "state": "APPROVED",
        "html_url": "https://github.com/acme/widgets/pull/7#pullrequestreview-81",
        "submitted_at": "2026-01-15T10:30:00Z",
    }

    item = normalize_review(review, repo_full_name="acme/widgets", pr_number=7)

    assert item is None


def test_review_with_a_none_body_is_skipped() -> None:
    review = {
        "id": 82,
        "user": {"login": "octocat"},
        "body": None,
        "state": "CHANGES_REQUESTED",
        "html_url": "https://github.com/acme/widgets/pull/7#pullrequestreview-82",
        "submitted_at": "2026-01-15T10:30:00Z",
    }

    item = normalize_review(review, repo_full_name="acme/widgets", pr_number=7)

    assert item is None


def test_normalizes_a_review_comment() -> None:
    comment = {
        "id": 1,
        "path": "src/x.py",
        "user": {"login": "octocat"},
        "body": "Nit: rename this variable.",
        "html_url": "https://github.com/acme/widgets/pull/7#discussion_r1",
        "created_at": "2026-01-15T09:00:00Z",
    }

    item = normalize_review_comment(comment, repo_full_name="acme/widgets", pr_number=7)

    assert item.source == "github"
    assert item.source_type == "review_comment"
    assert item.external_id == "review-comment-1"
    assert item.body == "Nit: rename this variable."
    assert item.author == "octocat"
    assert item.occurred_at == datetime(2026, 1, 15, 9, 0, 0, tzinfo=UTC)
    assert item.extra == {
        "repo": "acme/widgets",
        "pr_number": 7,
        "kind": "comment",
        "path": "src/x.py",
    }


def test_review_and_review_comment_external_ids_never_collide() -> None:
    # Reviews and inline comments have separate id namespaces in GitHub's
    # API — the same numeric id could otherwise land as the same
    # `external_id` within the shared `review_comment` source_type.
    review = {
        "id": 1,
        "user": {"login": "octocat"},
        "body": "LGTM",
        "state": "APPROVED",
        "html_url": "https://github.com/acme/widgets/pull/7#pullrequestreview-1",
        "submitted_at": "2026-01-15T10:30:00Z",
    }
    comment = {
        "id": 1,
        "path": "src/x.py",
        "user": {"login": "octocat"},
        "body": "Nit.",
        "html_url": "https://github.com/acme/widgets/pull/7#discussion_r1",
        "created_at": "2026-01-15T09:00:00Z",
    }

    review_item = normalize_review(review, repo_full_name="acme/widgets", pr_number=7)
    comment_item = normalize_review_comment(comment, repo_full_name="acme/widgets", pr_number=7)

    assert review_item is not None
    assert review_item.external_id != comment_item.external_id

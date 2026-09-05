"""Read-only GitHub REST API calls. No writes — matches the connector's
scope in plan.md §5, even though the OAuth `repo` scope itself permits more
(see `provider.py`)."""

import base64
from typing import Any

import httpx

_API_BASE = "https://api.github.com"


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_recent_repos(access_token: str, limit: int = 10) -> list[dict[str, Any]]:
    """Repos the authenticated user owns or collaborates on, most recently pushed first."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/user/repos",
            headers=_headers(access_token),
            params={"sort": "pushed", "direction": "desc", "per_page": limit},
        )
        response.raise_for_status()
        repos: list[dict[str, Any]] = response.json()
        return repos


async def list_recent_pull_requests(
    access_token: str, owner: str, repo: str, limit: int = 20
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls",
            headers=_headers(access_token),
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": limit},
        )
        response.raise_for_status()
        pulls: list[dict[str, Any]] = response.json()
        return pulls


async def list_recent_commits(
    access_token: str, owner: str, repo: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Commit messages only — no diffs/patches. Already chronological
    (most recent first) on the default branch; no sort param needed."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/commits",
            headers=_headers(access_token),
            params={"per_page": limit},
        )
        response.raise_for_status()
        commits: list[dict[str, Any]] = response.json()
        return commits


async def list_directory_contents(
    access_token: str, owner: str, repo: str, path: str = ""
) -> list[dict[str, Any]]:
    """Immediate children of `path` (files and subdirectories) — used for
    live directory browsing (`engine/code_context`), not ingestion. `path`
    is the empty string for the repo root, matching GitHub's own API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        data = response.json()
        # GitHub returns a single object (not a list) when `path` points at
        # a file rather than a directory — callers only browse directories.
        entries: list[dict[str, Any]] = data if isinstance(data, list) else [data]
        return entries


async def get_file_content(access_token: str, owner: str, repo: str, path: str) -> str | None:
    """Decoded text content of a single file at the repo's default
    branch — the same `/contents/{path}` endpoint `list_directory_contents`
    uses, but decoding the `content` field that only shows up when `path`
    points at a file (directory listings never carry it). Used for
    ingesting decision-doc markdown, not live browsing.

    Returns `None` for a 404 (path doesn't exist) or a directory — the
    caller is probing candidate decision-doc folders that most repos
    won't have, so "doesn't exist" is an expected outcome, not an error."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(access_token),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("type") != "file":
            return None
        content_b64: str = data.get("content", "")
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")


async def get_latest_commit_for_path(
    access_token: str, owner: str, repo: str, path: str
) -> dict[str, Any] | None:
    """Most recent commit that touched `path` — GitHub's Contents API
    (`get_file_content` above) returns the blob itself, not commit
    history, so dating/attributing a decision doc needs this separate
    call. `None` if the path has no commit history GitHub will return
    (shouldn't happen for a file `get_file_content` just confirmed
    exists, but a repo with a truncated/rewritten history is possible)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/commits",
            headers=_headers(access_token),
            params={"path": path, "per_page": 1},
        )
        response.raise_for_status()
        commits: list[dict[str, Any]] = response.json()
        return commits[0] if commits else None


async def list_workflow_runs(
    access_token: str, owner: str, repo: str, *, per_page: int = 50
) -> list[dict[str, Any]]:
    """Every GitHub Actions workflow run for the repo, most recent first —
    one call covers every workflow (each run object carries its own
    `name`), no separate "list workflows" call needed. Used by
    `features/flaky_tests` (ADR 0018) — no other module reaches into
    Actions. Unlike every other list endpoint in this file, the response
    is `{"total_count": N, "workflow_runs": [...]}`, not a bare array —
    unwrapped here so callers get the same plain-list shape as everything
    else."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/actions/runs",
            headers=_headers(access_token),
            params={"per_page": per_page},
        )
        response.raise_for_status()
        data = response.json()
        runs: list[dict[str, Any]] = data.get("workflow_runs", [])
        return runs


async def get_workflow_run_attempt(
    access_token: str, owner: str, repo: str, run_id: int, attempt_number: int
) -> dict[str, Any]:
    """One specific attempt's own recorded outcome — unlike
    `list_workflow_runs`, which only ever reflects a run's *latest*
    attempt. Used by `features/flaky_tests` to fetch attempt 1's real
    `conclusion` for a re-run, so a same-commit re-run's flakiness
    evidence can be a genuine before/after comparison instead of an
    assumption (see `WorkflowRun.first_attempt_conclusion`)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        run: dict[str, Any] = response.json()
        return run


async def list_run_artifacts(
    access_token: str, owner: str, repo: str, run_id: int
) -> list[dict[str, Any]]:
    """Artifacts attached to one workflow run — same `{"total_count",
    "artifacts": [...]}` envelope shape as `list_workflow_runs`, unwrapped
    the same way. Used by `features/flaky_tests`'s best-effort
    individual-test-case parsing (ADR 0019)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        data = response.json()
        artifacts: list[dict[str, Any]] = data.get("artifacts", [])
        return artifacts


async def download_artifact(access_token: str, owner: str, repo: str, artifact_id: int) -> bytes:
    """Downloads one artifact as a zip. GitHub responds with a redirect
    to a temporary blob URL — `follow_redirects=True` is needed here
    specifically; every other call in this file only ever hits GitHub's
    API directly and never redirects. Binary; callers are expected to
    check the artifact's `size_in_bytes` (from `list_run_artifacts`)
    before calling this, not after."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        return response.content


async def list_pr_reviews(
    access_token: str, owner: str, repo: str, pr_number: int
) -> list[dict[str, Any]]:
    """Top-level review verdicts (APPROVED/CHANGES_REQUESTED/COMMENTED) on
    one PR — used during ingestion, capped to the most-recently-updated
    PRs per repo (`connectors/github/ingest.py`'s `_REVIEW_FETCH_LIMIT`,
    see ADR 0016)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        reviews: list[dict[str, Any]] = response.json()
        return reviews


async def list_pr_review_comments(
    access_token: str, owner: str, repo: str, pr_number: int
) -> list[dict[str, Any]]:
    """Inline code comments on one PR — has `path`/`line`, unlike the
    top-level reviews above. Same ingestion cap applies."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        comments: list[dict[str, Any]] = response.json()
        return comments


async def get_commit(access_token: str, owner: str, repo: str, sha: str) -> dict[str, Any]:
    """Single commit, including a `files` array — unlike
    `list_recent_commits` (used for ingestion, which deliberately omits
    diffs/files, see ADR 0010), this endpoint returns exactly which files
    the commit touched. Used live, on demand, by the ticket/PR-first
    search entry point (ADR 0015) — never during ingestion itself."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/commits/{sha}",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data


async def list_pull_request_files(
    access_token: str, owner: str, repo: str, pr_number: int
) -> list[dict[str, Any]]:
    """Files changed by one PR — same "resolve on demand, not during
    ingestion" reasoning as `get_commit` above."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files",
            headers=_headers(access_token),
        )
        response.raise_for_status()
        files: list[dict[str, Any]] = response.json()
        return files


async def get_tree_recursive(access_token: str, owner: str, repo: str, ref: str) -> dict[str, Any]:
    """Every blob/tree in the whole repo at `ref`, in one call — used for
    whole-directory blame aggregation (`engine/code_context`), where
    walking subdirectories one at a time via `list_directory_contents`
    would mean one REST call per nested folder. `ref` accepts a branch
    name directly, same as `graphql_client.get_blame`'s `ref` param.

    Returns the raw response dict (`{"tree": [...], "truncated": bool}`)
    — callers check `truncated` themselves, since what "too large" means
    depends on what they're about to do with the result."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/git/trees/{ref}",
            headers=_headers(access_token),
            params={"recursive": "1"},
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

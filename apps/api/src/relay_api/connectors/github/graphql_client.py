"""GitHub's GraphQL API (v4) — a separate surface from `client.py`'s REST
calls, needed for exactly one thing REST can't do: git blame. Same OAuth
token, same `repo` scope already granted for the REST calls — no new
consent screen.

One query does the whole job: line ranges, the commit that last touched
each range, its author, AND the originating pull request (title/body,
needed for Jira ticket-key extraction in `features/archaeology`) — all in
a single round trip, rather than blame + a separate "find the PR for this
commit" call per commit.
"""

from typing import Any

import httpx

_GRAPHQL_URL = "https://api.github.com/graphql"

_BLAME_QUERY = """
query($owner: String!, $repo: String!, $ref: String!, $path: String!) {
  repository(owner: $owner, name: $repo) {
    object(expression: $ref) {
      ... on Commit {
        blame(path: $path) {
          ranges {
            startingLine
            endingLine
            commit {
              oid
              message
              committedDate
              url
              author {
                name
                user { login }
              }
              associatedPullRequests(first: 1) {
                nodes { number title url body }
              }
            }
          }
        }
      }
    }
  }
}
"""


class GraphQLError(Exception):
    """Raised when GitHub's GraphQL endpoint returns a top-level `errors`
    array — e.g. an unknown ref or path. Distinct from an HTTP-level
    failure (`httpx.HTTPStatusError`), which GraphQL mostly doesn't use —
    a bad query still comes back as 200 with an `errors` field."""


async def get_blame(
    access_token: str, owner: str, repo: str, ref: str, path: str
) -> dict[str, Any] | None:
    """Returns the raw `blame` object (`{"ranges": [...]}`) or `None` if
    the ref/path resolved to nothing blame-able (binary file, empty file,
    or the object simply isn't a Commit) — the caller decides what "no
    blame data" means for its endpoint, this layer just reports it."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            _GRAPHQL_URL,
            json={
                "query": _BLAME_QUERY,
                "variables": {"owner": owner, "repo": repo, "ref": ref, "path": path},
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        payload = response.json()

    if payload.get("errors"):
        raise GraphQLError(str(payload["errors"]))

    repository = payload.get("data", {}).get("repository")
    if repository is None:
        raise GraphQLError(f"Unknown repository: {owner}/{repo}")

    commit_object = repository.get("object")
    if commit_object is None:
        raise GraphQLError(f"Unknown ref: {ref}")

    blame: dict[str, Any] | None = commit_object.get("blame")
    return blame

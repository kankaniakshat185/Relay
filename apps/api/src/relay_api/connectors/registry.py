"""Single place that knows all three connector providers exist. Each
provider module (`github.provider`, `slack.provider`, `jira.provider`)
structurally satisfies `ConnectorProvider` — a module works fine here since
these are stateless, config-driven functions, not something needing
per-instance state."""

from relay_api.connectors.base import ConnectorProvider, RefreshableConnectorProvider
from relay_api.connectors.github import provider as github_provider
from relay_api.connectors.jira import provider as jira_provider
from relay_api.connectors.slack import provider as slack_provider

ALL_PROVIDERS: tuple[str, ...] = ("github", "slack", "jira")

# Slack's bot-install tokens don't expire, so it's the one provider absent
# here. GitHub is refreshable even though its tokens *usually* don't
# expire — whether they do depends on a per-OAuth-App owner setting
# ("expire user authorization tokens"), found live in Phase 2 (see the
# retro) — `ensure_valid_access_token` only ever calls this when
# `expires_at` is actually set, so it's a no-op the rest of the time.
_REFRESHABLE_PROVIDERS: dict[str, RefreshableConnectorProvider] = {
    "github": github_provider,
    "jira": jira_provider,
}


def get_connector_providers() -> dict[str, ConnectorProvider]:
    return {
        "github": github_provider,
        "slack": slack_provider,
        "jira": jira_provider,
    }


def get_refreshable_provider(provider_name: str) -> RefreshableConnectorProvider | None:
    """None means "nothing to refresh for this provider" — a normal,
    expected case, not an error condition for callers to special-case."""
    return _REFRESHABLE_PROVIDERS.get(provider_name)

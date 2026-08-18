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

# Only Jira issues short-lived access tokens today — GitHub's classic OAuth
# app and Slack's bot-install flow don't. Adding a fourth provider (or
# switching GitHub to a GitHub App) means adding a `refresh_access_token`
# to that provider module and one entry here, nothing else.
_REFRESHABLE_PROVIDERS: dict[str, RefreshableConnectorProvider] = {
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

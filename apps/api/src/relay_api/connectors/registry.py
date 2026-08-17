"""Single place that knows all three connector providers exist. Each
provider module (`github.provider`, `slack.provider`, `jira.provider`)
structurally satisfies `ConnectorProvider` — a module works fine here since
these are stateless, config-driven functions, not something needing
per-instance state."""

from relay_api.connectors.base import ConnectorProvider
from relay_api.connectors.github import provider as github_provider
from relay_api.connectors.jira import provider as jira_provider
from relay_api.connectors.slack import provider as slack_provider

ALL_PROVIDERS: tuple[str, ...] = ("github", "slack", "jira")


def get_connector_providers() -> dict[str, ConnectorProvider]:
    return {
        "github": github_provider,
        "slack": slack_provider,
        "jira": jira_provider,
    }

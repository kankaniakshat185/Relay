from relay_api.connectors.registry import ALL_PROVIDERS, get_connector_providers


def test_registry_has_exactly_the_three_scoped_providers() -> None:
    providers = get_connector_providers()

    assert set(providers.keys()) == {"github", "slack", "jira"}
    assert set(ALL_PROVIDERS) == {"github", "slack", "jira"}


def test_each_provider_exposes_the_required_interface() -> None:
    for name, provider in get_connector_providers().items():
        assert provider.name == name
        assert callable(provider.authorization_url)
        assert callable(provider.exchange_code)

from relay_api.connectors.slack.normalize import normalize_message


def test_normalizes_a_regular_message() -> None:
    message = {"text": "the retry bug is back", "user": "U123", "ts": "1704067200.000100"}

    item = normalize_message(message, channel_id="C1", channel_name="eng-alerts", team_id="T1")

    assert item is not None
    assert item.source == "slack"
    assert item.source_type == "message"
    assert item.external_id == "C1:1704067200.000100"
    assert item.author == "U123"
    assert item.extra == {"channel": "eng-alerts", "channel_id": "C1"}


def test_skips_empty_text_message() -> None:
    message = {"text": "", "user": "U123", "ts": "1704067200.000100"}

    assert normalize_message(message, channel_id="C1", channel_name="general", team_id="T1") is None


def test_skips_system_subtype_messages() -> None:
    message = {
        "text": "octocat has joined the channel",
        "user": "U123",
        "ts": "1704067200.000100",
        "subtype": "channel_join",
    }

    assert normalize_message(message, channel_id="C1", channel_name="general", team_id="T1") is None

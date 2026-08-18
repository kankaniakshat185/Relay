from relay_api.connectors.text_utils import truncate_title


def test_short_text_is_unchanged() -> None:
    assert truncate_title("Fix retry logic") == "Fix retry logic"


def test_long_text_is_truncated_at_a_word_boundary_with_ellipsis() -> None:
    text = "word " * 100  # 500 chars, well past the limit

    result = truncate_title(text)

    assert len(result) <= 201
    assert result.endswith("…")
    assert not result[:-1].endswith(" ")  # truncated at a word boundary, no trailing space


def test_embedded_newlines_and_whitespace_are_collapsed() -> None:
    assert truncate_title("Fix retry\n\nlogic   here") == "Fix retry logic here"

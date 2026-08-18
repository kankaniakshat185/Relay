"""Shared text handling for normalizers. `ingested_items.title` is a
bounded VARCHAR — no upstream API's own field can be trusted to respect
that, even ones that look title-shaped. Found the hard way: a GitHub
commit message with no line breaks makes `message.splitlines()[0]` return
the *entire* message, which blew past the column limit on a real commit
from a real repo, not a crafted edge case.
"""

_TITLE_MAX_LENGTH = 200


def truncate_title(text: str) -> str:
    text = " ".join(text.split())  # collapse embedded newlines/whitespace too
    if len(text) <= _TITLE_MAX_LENGTH:
        return text
    return text[:_TITLE_MAX_LENGTH].rsplit(" ", 1)[0] + "…"

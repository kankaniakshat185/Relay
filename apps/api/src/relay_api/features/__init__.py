"""Query-mode features (context_search, archaeology, who_to_ask, notes,
weekly_digest) and one standalone subsystem (flaky_tests).

A `dependency_alerts` module lived here too, in the original plan — cut
before anything beyond a stub was built; see
docs/decisions/0004-cut-dependency-alert-bot.md for why.

Module boundary rule: each feature owns its router/service/schema and may
only import from `engine/`, never from a sibling feature. See plan.md §2.
"""

"""Query-mode features (context_search, archaeology, who_to_ask) and the two
standalone subsystems (flaky_tests, dependency_alerts).

Module boundary rule: each feature owns its router/service/schema and may
only import from `engine/`, never from a sibling feature. See plan.md §2.
"""

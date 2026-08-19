"""The shared correlation/retrieval engine — Relay's core architectural bet.

`features/*` query this package and only this package; it never imports from
`features/*`. Built out starting Phase 1 (ingestion, indexing) and Phase 2
(ranking, code_context) — see plan.md §5.
"""

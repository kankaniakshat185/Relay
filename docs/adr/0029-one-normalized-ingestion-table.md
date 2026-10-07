# ADR 0029: One normalized ingestion table, not per-source or per-feature tables

**Status:** Accepted — recorded retroactively. The decision predates this ADR; ADR 0006 already relies on it for vector search.

## What

Every searchable item from every source lives in one physical table,
`ingested_items` (`engine/ingestion/models.py`). GitHub PRs, commits, reviews,
decision docs, Slack messages, Jira issues, and user notes are all rows in it.
Each row has the same shape: `source`, `source_type`, `external_id`, `title`,
`body`, `url`, `author`, `occurred_at`, an `extra` JSONB field, and the
indexing-owned `embedding` and `search_vector` columns.

Each connector converts provider JSON into one shared contract,
`NormalizedItem` (`engine/ingestion/schemas.py`), and nothing else in the engine
sees provider-specific shapes. Ingestion writes through a single function,
`upsert_items`.

## Why

**One query, not a join.** The engine's core operation is "find items matching
structured filters (source, time window, entity) and rank them by keyword and
vector similarity." Against one table, that's a single SQL statement. Against
per-source tables, every feature would need to know which tables to query,
run one query per table, and merge and re-rank the results in application
code. That's the same argument ADR 0006 makes for vectors, extended to the
rows themselves.

**A new source is a new connector, not a new query path.** Adding a source
means writing a connector that produces `NormalizedItem`s. Context Search,
Weekly Digest, Incident Correlation, and Decision Debt pick it up with no change,
because they already query the one table. Notes shows this working: user-written
notes are mirrored in as a fourth source (ADR 0021) and are searchable by every
query mode without new query code.

**One dedupe rule.** Identity is `(user_id, source, source_type, external_id)`
(a unique constraint). Re-ingesting an item is an upsert, not a special case per
source. The same mechanism that keeps GitHub idempotent keeps notes idempotent.

**Relevance across sources needs one candidate pool.** A keyword or vector score
is only comparable across items that were scored against the same index. Per-table
retrieval would produce separate ranked lists that can't be merged meaningfully
without a shared scale.

## How

- `source` is a closed set (`github`, `slack`, `jira`, `notes`). `source_type`
  is a closed set of kinds (`pull_request`, `commit`, `message`, `issue`,
  `review_comment`, `note`, `decision_doc`). Both are `Literal` types in
  `engine/ingestion/schemas.py`, so a connector can't invent a value silently.
- Source-specific display data goes into `extra` (JSONB). Examples: repo name,
  channel name, file path, commit SHA.
- Each row's identity comes from the provider's own id, passed through as
  `external_id`.
- Indexing-owned columns (`embedding`, `search_vector`) start null and are
  filled by a separate job. Updates reset them to null, so changed items get
  re-indexed (see `upsert_items`).
- Features read through a small set of engine functions: `search()` for hybrid
  relevance (ADR 0006), `get_items_since()` for time windows, and
  `find_related()` for correlation (ADR 0012, 0014). No feature queries the
  table directly for retrieval.

## Consequences

**Gains:**
- Every query mode works over every source with no per-source code.
- Adding a source touches connectors only.
- One index strategy (GIN on `search_vector`, HNSW on `embedding`) covers everything.
- One place to reason about dedupe, freshness, and cost.

**Costs, stated honestly:**
- **`extra` is untyped.** The database can't enforce what's in it. Anything
  that needs to be queried should be a real column, and the normalization
  contract says so. In practice this rule is not fully held:
  - Correlation matches Jira issues by `extra["key"]`
    (`engine/correlation/service.py`, `find_similar_jira_issues`).
  - Review-comment lookup filters on `extra.pr_number`
    (`connectors/github/normalize.py` documents this, and `find_review_comments_for_pr`
    relies on it).
  
  These work because the values are stable, but they're exactly the queries the
  contract says should move to real columns. Promoting `key` and `pr_number` to
  first-class, indexed columns is the cleanup this ADR points to.
- **The table grows with every source.** At this scale that's fine. At large
  scale, a single table is a single point of contention for writes and vacuum.
  Partitioning by `user_id` or `source` would be the first step.
- **Shared columns don't fit every source.** Some sources don't naturally have
  an `author` or a meaningful `url`. The contract allows nulls there, but
  consumers must handle them.
- **Per-source schema validation moves to the connector.** A bug in one
  connector's normalization can write bad rows that look valid to the engine.
  Connector tests (`tests/unit/connectors/`) are the only guard.

**Revisit if:** a source needs rich, typed, source-specific queries that can't
be expressed as a shared retrieval shape, or if write volume makes the single
table a bottleneck.

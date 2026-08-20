# ADR 0021: Personal Notes — a fourth source, mirrored into the shared engine

**Status:** Accepted

## What

Relay's first user-authored content, and its fourth searchable source
alongside GitHub, Slack, and Jira. Not in `plan.md`'s original five —
scoped live after the user asked whether a notes feature was useful and
how hard it'd be to build, then extended twice more in the same session
(single link → a list of links; "annotate this" from one page → three).

- `features/notes/models.py`: `Note`, a new, standalone table (`notes`) —
  title, body, tags, and `links: JSONB` — zero or more denormalized
  references (source, URL, title) to existing GitHub/Slack/Jira items a
  note is annotating. Started as a single optional reference; became a
  list once it was clear one note reasonably wants to tie together
  several items (a PR *and* the Slack thread *and* the Jira ticket it
  closed) — see "From one link to many" below.
- `features/notes/service.py`: every create/update **mirrors** the note
  into `engine.ingestion.models.IngestedItem` (`source="notes"`) via the
  same `upsert_items`/`index_items` every connector already uses, and
  embeds it **synchronously** — there's nothing external to poll, the
  note was just written directly.
- New `/notes` page: list, inline create/edit, tags (with existing-tag
  suggestions and click-to-filter the list), Markdown export, and an
  "annotate this" flow — a small "+ Annotate" action on Search,
  Archaeology, and Who Should I Ask results that lets you either start a
  new note or attach the item to one you already have, reusing the real
  ingested title rather than retyping anything.
- `engine.ingestion.schemas.Source`/`SourceType` gain `"notes"`/`"note"`
  — the one change outside `features/notes` itself.

## Why a dedicated `notes` table, not writing straight into `ingested_items`

`IngestedItem` already has an `extra: JSONB` bag GitHub/Jira use for
source-specific display fields — tags and a linked-item reference could
technically live there instead of a new table. Rejected: `ingested_items`
documents a strict column-ownership discipline ("`engine/ingestion`
writes X; `engine/indexing` writes Y") — nothing today PATCH-edits a row
by field the way notes need to (retitle, edit body, retag, independently
of each other). Same reasoning ADR 0018 used for Flaky Tests ("doesn't
fit `ingested_items`'s shape or its consumers' assumptions"): Notes owns
its row in its own table; a save mirrors a copy into `ingested_items`
purely so the existing retrieval pipeline can see it. Delete removes
both, via a direct `source="notes"` + `external_id` lookup — no FK
between the two tables, deliberately (matches every connector: nothing
in `ingested_items` ever holds a foreign key back to the row that
produced it).

## Why the mirror was cheap: `engine.indexing` already didn't care where content came from

Read before writing any code, not assumed: `engine.indexing.service.
index_items` embeds whatever `title`/`body` it's handed — zero
source-specific logic. `engine.ingestion.service.upsert_items` is the one
write path every connector already shares. Neither assumes its caller is
an external API poller. Adding a fourth, user-authored source meant
reusing both functions directly, not writing a parallel retrieval path —
this is ADR 0005's "one engine, many query modes" holding up exactly as
designed for a source nobody had in mind when it was written.

## Synchronous indexing, and why a failed embed doesn't fail the save

Every other source is ingested on a 15-minute Celery cadence because
there's a remote API to poll. A note doesn't need polling — it's already
in Relay's own database the moment it's saved — so `_mirror_into_engine`
calls `index_items` directly in the request, one item, immediately after
the note itself commits. If the embed call fails (quota, a transient
provider error), that's caught and logged, not raised: the note is
already saved and fully usable from the Notes page by the time indexing
runs, and a downstream indexing hiccup must not take the primary save
down with it (same discipline as Build 2's JUnit parser — a side effect
degrades gracefully). A note that fails to index this way just isn't
searchable until its next edit retries the same path; there's no
separate backfill job for this today; see open items.

## Every link is a denormalized snapshot, not a live reference

Each entry in `Note.links` (`{source, url, title}`) is copied at the
moment it's added, not looked up from `IngestedItem` on read, and
there's no foreign key. A linked item can be re-ingested (title
changes), or fall out of the connector's fetch window and disappear from
`ingested_items` entirely — a note should still show what it was
annotating when the link was made, not go stale, silently repoint at
something else, or 404. `NoteLink.source` is scoped to
`github`/`slack`/`jira` specifically (not `notes` itself) — annotating
one note with another isn't a case this supports.

## From one link to many, and why removal is by index

The first version gave a note at most one link, set once at creation.
Reworked into a list (`links: list[NoteLink]`) once "annotate this" was
extended to Archaeology and Who Should I Ask — both pages surface many
more linkable items per screen (a commit, its PR, its Jira ticket,
related Slack messages, similar past issues, review comments) than
Search's flat result list did, and the natural use case that fell out of
that was tying several of them to *one* note (a PR, its Slack thread, and
the Jira ticket it closed, all on the same note about "why this exists"),
not just one link per note.

Two endpoints, mirroring the two ways a link gets added:
- `create_note` seeds `links` at creation (the "+ Create new note" half
  of the annotate flow).
- `POST /{note_id}/links` appends to an existing note (the "or add to an
  existing note" half) — the Notes page reads the pending link off the
  URL and, instead of always opening a fresh composer, offers a list of
  existing notes to attach to directly.

`DELETE /{note_id}/links/{index}` removes one, **by index, not by
(source, url) match** — a note can in principle reference the same item
twice, and matching on content wouldn't unambiguously say which one to
drop. Both endpoints return the full updated note; neither touches
title/body, so neither re-triggers `_mirror_into_engine` — a link is
display-only metadata as far as search/indexing is concerned, same as
tags.

## Notes have no detail page — search results deep-link via `?highlight=`, not a route

Notes is a flat list, not list+detail — matching how the rest of this
app doesn't really have a detail-view pattern either. A note's `url`
(what `ingested_items` stores, what Search results link to) is
`/notes?highlight={id}`, not `/notes/{id}` — there's no route to 404
into. The Notes page reads `highlight` and
scrolls the matching row into view. Left deliberately un-stripped from
the URL after use (unlike the `?new=…` annotate-flow param, which *is*
stripped) — a bookmarked or shared link to one specific note should keep
highlighting it on reload, not lose that on the first refresh.

## Live-verified against the real embeddings pipeline, not just mocks

A note was created directly against the dev database with **no mocking**
— the real Gemini embedding call — and immediately queried through
`features.context_search.service.search`: it came back as the top result
for a semantically matching (not keyword-matching) query, then cleanly
deleted (both the `notes` row and its `ingested_items` mirror). This is
the actual claim this ADR makes — "a note becomes real, searchable
context" — proven against the real pipeline, not asserted from the
architecture alone.

## What this does NOT do

No bulk import from external files (Notion export, markdown files) —
scoped out during the original discussion in favor of the on-brand
"annotate an existing item" flow, which reuses data already in Relay
instead of solving a separate file-parsing problem. No backfill/retry
job for notes whose synchronous embed call failed — rare, and editing
the note retries it for free, so a dedicated job wasn't built for this
version. No note-to-note linking. Tag filtering on the Notes page is
client-side only, over whatever `list_notes` already returned — no
backend filter/pagination endpoint; fine at today's scale, would need
revisiting if a single user's note count ever got large.

"Annotate this" lives on Search, Archaeology, and Who Should I Ask —
deliberately not Flaky Test Investigator: flaky-test runs aren't part of
the searchable `ingested_items` corpus at all (a standalone table, ADR
0018), and "why is this test flaky" reads as a different kind of note
(ops/debugging) than "why does this code exist" (context recovery),
which is what this feature was actually built around.

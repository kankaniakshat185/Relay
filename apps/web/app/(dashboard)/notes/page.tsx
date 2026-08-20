"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, type FormEvent, useEffect, useMemo, useState } from "react";

import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type LinkedSource,
  type Note,
  type NoteCreateInput,
  type NoteLink,
  SOURCE_LABELS,
  addLinkToNote,
  createNote,
  deleteAllNotes,
  deleteNote,
  downloadNotesExport,
  fetchNotes,
  removeLinkFromNote,
  updateNote,
} from "@/lib/notes";

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return "Your session expired — sign in again.";
    return `Request failed (${err.status}).`;
  }
  return "Couldn't reach the server — check that the backend is running.";
}

function normalizeTag(raw: string): string {
  // Lowercased so "Backend" and "backend" can't silently become two
  // different tags — the whole point of showing existing tags at all is
  // consistent tagging, and case is the easiest way for that to
  // fragment.
  return raw.trim().toLowerCase();
}

const INPUT_CLASS =
  "border-line text-ink placeholder:text-muted focus:border-brand border px-3 py-2 text-sm outline-none";

function TagPicker({
  tags,
  existingTags,
  onChange,
}: {
  tags: string[];
  existingTags: string[];
  onChange: (tags: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function commit(rawText: string) {
    const tag = normalizeTag(rawText);
    if (tag && !tags.includes(tag)) {
      onChange([...tags, tag]);
    }
    setDraft("");
  }

  function removeTag(tag: string) {
    onChange(tags.filter((t) => t !== tag));
  }

  const suggestions = existingTags.filter((t) => !tags.includes(t));

  return (
    <div>
      {tags.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => removeTag(tag)}
              className="border-brand text-brand hover:bg-brand hover:text-paper-white flex items-center gap-1.5 border px-2 py-1 text-xs font-medium tracking-[0.05em] uppercase transition-colors"
            >
              {tag}
              <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      )}
      <input
        type="text"
        value={draft}
        onChange={(e) => {
          const value = e.target.value;
          // A trailing comma commits the tag typed so far, same as
          // pressing Enter — the natural way people type comma-separated
          // tags without reaching for the keyboard's Enter key each time.
          if (value.endsWith(",")) {
            commit(value.slice(0, -1));
          } else {
            setDraft(value);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(draft);
          }
        }}
        onBlur={() => commit(draft)}
        placeholder={tags.length > 0 ? "Add another tag…" : "Tags — press Enter to add"}
        className={INPUT_CLASS}
      />
      {suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className="text-muted text-xs">Existing:</span>
          {suggestions.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => onChange([...tags, tag])}
              className="text-muted hover:text-brand text-xs font-medium tracking-[0.05em] uppercase transition-colors"
            >
              + {tag}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** One "↳ Source — title" reference line, used both for a note's own
 * saved links and for the pending link shown while composing/attaching
 * — the source label is what makes it unambiguous which search result
 * (GitHub, Slack, or Jira) a note actually points at. */
function LinkReference({
  link,
  href,
  onRemove,
}: {
  link: NoteLink;
  href?: string;
  onRemove?: () => void;
}) {
  const label = (
    <>
      <span className="text-muted uppercase">{SOURCE_LABELS[link.source]}</span>
      <span className="text-muted"> — </span>
      <span className={href ? "" : "text-ink"}>{link.title}</span>
    </>
  );
  return (
    <p className="flex items-baseline gap-2 text-xs">
      <span>
        <span className="text-muted mr-1">↳</span>
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="hover:text-brand text-ink transition-colors"
          >
            {label}
          </a>
        ) : (
          label
        )}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove this link"
          className="text-muted hover:text-brand shrink-0 transition-colors"
        >
          ×
        </button>
      )}
    </p>
  );
}

interface ComposerPrefill {
  id?: string;
  title?: string;
  body?: string;
  tags?: string[];
  link?: NoteLink | null;
}

function NoteComposer({
  initial,
  existingTags,
  onCancel,
  onSaved,
}: {
  initial?: ComposerPrefill;
  existingTags: string[];
  onCancel: () => void;
  onSaved: (note: Note) => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (saving) return;
    if (!title.trim()) {
      setError("Give it a title first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = initial?.id
        ? await updateNote(initial.id, { title, body, tags })
        : await createNote({
            title,
            body,
            tags,
            links: initial?.link ? [initial.link] : [],
          } satisfies NoteCreateInput);
      onSaved(saved);
    } catch (err) {
      console.error(err);
      setError(describeError(err));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="border-line mt-6 flex flex-col gap-4 border p-6">
      {initial?.link && <LinkReference link={initial.link} />}
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title"
        autoFocus
        className={INPUT_CLASS}
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Write your note…"
        rows={5}
        className={`${INPUT_CLASS} leading-relaxed`}
      />
      <TagPicker tags={tags} existingTags={existingTags} onChange={setTags} />
      {error && <p className="text-brand text-sm">{error}</p>}
      <div className="mt-3 flex items-center gap-5">
        <button
          type="submit"
          disabled={saving}
          className="border-brand text-brand hover:bg-brand hover:text-paper-white border px-3 py-1.5 text-xs font-medium tracking-[0.1em] uppercase transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : initial?.id ? "Save changes" : "Add note"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="text-muted hover:text-ink text-xs font-medium tracking-[0.15em] uppercase transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Shown when arriving via "+ Annotate" from Search/Archaeology/Who
 * Should I Ask — offers attaching the item you were looking at to a new
 * note or an already-existing one, rather than always creating a new
 * note. A narrow editorial column, not a bordered panel filling the
 * viewport — the mental model is a short, linear decision (what am I
 * attaching → new note or existing → save), not a dashboard widget. */
function PendingLinkPanel({
  link,
  notes,
  existingTags,
  onAttach,
  onDismiss,
  onNoteSaved,
}: {
  link: NoteLink;
  notes: Note[];
  existingTags: string[];
  onAttach: (noteId: string) => void;
  onDismiss: () => void;
  onNoteSaved: (note: Note) => void;
}) {
  const [composing, setComposing] = useState(false);

  return (
    <div className="mt-8">
      <SectionLabel tone="brand">Attach this item</SectionLabel>
      <div className="mt-3">
        <LinkReference link={link} />
      </div>
      <Rule className="mt-6" />

      {composing ? (
        <NoteComposer
          initial={{ link }}
          existingTags={existingTags}
          onCancel={() => setComposing(false)}
          onSaved={onNoteSaved}
        />
      ) : (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Create new note
          </SectionLabel>
          <button
            type="button"
            onClick={() => setComposing(true)}
            className="border-brand text-brand hover:bg-brand hover:text-paper-white mt-3 border px-3 py-1.5 text-xs font-medium tracking-[0.1em] uppercase transition-colors"
          >
            + Create new note
          </button>

          {notes.length > 0 && (
            <>
              <SectionLabel tone="muted" className="mt-8">
                Or add to an existing note
              </SectionLabel>
              <ul className="border-line mt-3 flex flex-col border-l">
                {notes.map((note) => (
                  <li key={note.id}>
                    <button
                      type="button"
                      onClick={() => onAttach(note.id)}
                      className="group flex w-full items-baseline justify-between gap-4 py-2 pl-4 text-left transition-colors"
                    >
                      <span className="flex items-baseline gap-2">
                        <span className="text-ink group-hover:text-brand text-sm transition-colors">
                          {note.title}
                        </span>
                        <span className="text-muted text-xs">
                          {new Date(note.updated_at).toLocaleDateString()}
                        </span>
                      </span>
                      <span className="text-muted group-hover:text-brand shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors">
                        Attach →
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}

          <button
            type="button"
            onClick={onDismiss}
            className="text-muted hover:text-ink mt-8 block text-xs font-medium tracking-[0.1em] uppercase opacity-70 transition-colors"
          >
            ← Cancel
          </button>
        </>
      )}
    </div>
  );
}

function NoteRow({
  note,
  highlighted,
  onEdit,
  onDelete,
  onRemoveLink,
}: {
  note: Note;
  highlighted: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onRemoveLink: (linkIndex: number) => void;
}) {
  return (
    <li
      id={`note-${note.id}`}
      className={`border-line border-b py-6 transition-colors ${
        highlighted ? "border-l-brand -ml-4 border-l-2 pl-4" : ""
      }`}
    >
      <p className="font-serif text-xl text-ink sm:text-2xl">{note.title}</p>
      {note.body && (
        <p className="text-muted mt-2 max-w-2xl text-sm leading-relaxed whitespace-pre-wrap">
          {note.body}
        </p>
      )}
      {note.links.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          {note.links.map((link, i) => (
            <LinkReference
              key={`${link.url}-${i}`}
              link={link}
              href={link.url}
              onRemove={() => onRemoveLink(i)}
            />
          ))}
        </div>
      )}
      <Metadata
        items={[
          note.tags.length > 0 ? note.tags.join(" · ") : null,
          new Date(note.updated_at).toLocaleDateString(),
        ]}
        className="mt-2"
      />
      <div className="mt-3 flex items-center gap-5">
        <button
          type="button"
          onClick={onEdit}
          className="text-muted hover:text-ink text-xs font-medium tracking-[0.15em] uppercase transition-colors"
        >
          Edit
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="text-muted hover:text-brand text-xs font-medium tracking-[0.15em] uppercase transition-colors"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

function NotesPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [notes, setNotes] = useState<Note[] | "loading">("loading");
  const [error, setError] = useState<string | null>(null);
  const [composer, setComposer] = useState<ComposerPrefill | "closed">("closed");
  const [activeTagFilter, setActiveTagFilter] = useState<string | null>(null);

  // Lazy initializer, not a state-derived-in-an-effect pattern — reads
  // the URL exactly once, on first render. Landing here via "+ Annotate"
  // carries `linkSource`/`linkUrl`/`linkTitle`; left in the URL until the
  // user resolves what to do with it (create new vs. attach to
  // existing), then cleared explicitly by whichever handler fires.
  const [pendingLink, setPendingLink] = useState<NoteLink | null>(() => {
    const source = searchParams.get("linkSource") as LinkedSource | null;
    const url = searchParams.get("linkUrl");
    const title = searchParams.get("linkTitle");
    if (!source || !url || !title) return null;
    return { source, url, title };
  });

  const existingTags = useMemo(() => {
    if (notes === "loading") return [];
    const seen = new Set<string>();
    for (const note of notes) {
      for (const tag of note.tags) seen.add(tag);
    }
    return Array.from(seen).sort();
  }, [notes]);

  const visibleNotes = useMemo(() => {
    if (notes === "loading") return "loading" as const;
    if (!activeTagFilter) return notes;
    return notes.filter((n) => n.tags.includes(activeTagFilter));
  }, [notes, activeTagFilter]);

  useEffect(() => {
    fetchNotes()
      .then((n) => {
        setNotes(n);
        setError(null);
      })
      .catch((err: unknown) => {
        console.error(err);
        setError(describeError(err));
      });
  }, []);

  const highlightId = searchParams.get("highlight");

  useEffect(() => {
    // Clicking a note in Search results lands here with `?highlight=` —
    // an imperative scroll, not React state, so it's fine to run every
    // time `notes` finishes loading. Deliberately left in the URL
    // afterward — a bookmarked or shared link to this exact note should
    // still highlight it on reload.
    if (!highlightId || notes === "loading") return;
    document
      .getElementById(`note-${highlightId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId, notes]);

  function clearPendingLinkParams() {
    setPendingLink(null);
    router.replace("/notes");
  }

  function handleSaved(note: Note) {
    setNotes((prev) => {
      if (prev === "loading") return [note];
      const withoutThis = prev.filter((n) => n.id !== note.id);
      return [note, ...withoutThis].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      );
    });
    setComposer("closed");
  }

  async function handleAttachToExisting(noteId: string) {
    if (!pendingLink) return;
    try {
      const updated = await addLinkToNote(noteId, pendingLink);
      handleSaved(updated);
      clearPendingLinkParams();
    } catch (err) {
      console.error(err);
      setError(describeError(err));
    }
  }

  async function handleDelete(id: string, title: string) {
    const confirmed = window.confirm(`Delete "${title}"? This can't be undone.`);
    if (!confirmed) return;
    try {
      await deleteNote(id);
      setNotes((prev) => (prev === "loading" ? prev : prev.filter((n) => n.id !== id)));
    } catch (err) {
      console.error(err);
      setError(describeError(err));
    }
  }

  async function handleRemoveLink(noteId: string, linkIndex: number) {
    try {
      const updated = await removeLinkFromNote(noteId, linkIndex);
      handleSaved(updated);
    } catch (err) {
      console.error(err);
      setError(describeError(err));
    }
  }

  async function handleExport() {
    try {
      await downloadNotesExport();
    } catch (err) {
      console.error(err);
      setError(describeError(err));
    }
  }

  async function handleDeleteAll() {
    if (notes === "loading" || notes.length === 0) return;
    const confirmed = window.confirm(
      `Delete all ${notes.length} note${notes.length === 1 ? "" : "s"}? This can't be undone.`
    );
    if (!confirmed) return;
    try {
      await deleteAllNotes();
      setNotes([]);
    } catch (err) {
      console.error(err);
      setError(describeError(err));
    }
  }

  return (
    <div>
      <SectionLabel tone="brand">Notes</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Your own context
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Freeform, or annotated onto a specific commit, PR, ticket, or Slack message — notes are
        indexed alongside everything else, so they show up in Search too.
      </p>

      <Rule className="mt-16" />

      <div className="mt-8 w-full lg:w-[60%]">
        <div className="flex items-center gap-5">
          {composer === "closed" && (
            <button
              type="button"
              onClick={() => setComposer({})}
              className="border-brand text-brand hover:bg-brand hover:text-paper-white border px-3 py-1.5 text-xs font-medium tracking-[0.1em] uppercase transition-colors"
            >
              + New note
            </button>
          )}
          <button
            type="button"
            onClick={handleExport}
            className="text-muted hover:text-ink text-xs font-medium tracking-[0.15em] uppercase transition-colors"
          >
            Export all
          </button>
          {notes !== "loading" && notes.length > 0 && (
            <button
              type="button"
              onClick={handleDeleteAll}
              className="text-muted hover:text-brand text-xs font-medium tracking-[0.15em] uppercase transition-colors"
            >
              Delete all
            </button>
          )}
        </div>

        {pendingLink && (
          <PendingLinkPanel
            link={pendingLink}
            notes={notes === "loading" ? [] : notes}
            existingTags={existingTags}
            onAttach={handleAttachToExisting}
            onDismiss={clearPendingLinkParams}
            onNoteSaved={(note) => {
              handleSaved(note);
              clearPendingLinkParams();
            }}
          />
        )}

        {composer !== "closed" && (
          <NoteComposer
            initial={composer}
            existingTags={existingTags}
            onCancel={() => setComposer("closed")}
            onSaved={handleSaved}
          />
        )}

        <Rule className="mt-10" />

        {notes !== "loading" && existingTags.length > 0 && (
          <div className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <SectionLabel tone="muted" className="mr-1">
              Filter
            </SectionLabel>
            {existingTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTagFilter((current) => (current === tag ? null : tag))}
                className={`text-xs font-medium tracking-[0.05em] uppercase transition-colors ${
                  activeTagFilter === tag ? "text-brand" : "text-muted hover:text-ink"
                }`}
              >
                {tag}
              </button>
            ))}
            {activeTagFilter && (
              <button
                type="button"
                onClick={() => setActiveTagFilter(null)}
                className="text-muted hover:text-ink text-xs font-medium tracking-[0.05em] uppercase transition-colors"
              >
                × Clear
              </button>
            )}
          </div>
        )}

        {error ? (
          <p className="text-brand mt-8 text-sm">{error}</p>
        ) : visibleNotes === "loading" ? (
          <p className="text-muted mt-8 text-sm">Loading…</p>
        ) : visibleNotes.length === 0 ? (
          <p className="text-muted mt-8 text-sm">
            {activeTagFilter ? `No notes tagged "${activeTagFilter}".` : "No notes yet."}
          </p>
        ) : (
          <ul className="mt-2">
            {visibleNotes.map((note) =>
              composer !== "closed" && composer.id === note.id ? null : (
                <NoteRow
                  key={note.id}
                  note={note}
                  highlighted={note.id === highlightId}
                  onEdit={() =>
                    setComposer({
                      id: note.id,
                      title: note.title,
                      body: note.body,
                      tags: note.tags,
                    })
                  }
                  onDelete={() => handleDelete(note.id, note.title)}
                  onRemoveLink={(linkIndex) => handleRemoveLink(note.id, linkIndex)}
                />
              )
            )}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function NotesPage() {
  return (
    <Suspense fallback={null}>
      <NotesPageContent />
    </Suspense>
  );
}

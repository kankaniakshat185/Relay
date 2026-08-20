import { API_URL, apiFetch } from "./api";

export type LinkedSource = "github" | "slack" | "jira";

/** Display label for a linked item's source — shown next to every
 * "↳ Linked to …" reference so it's never ambiguous which search result
 * (GitHub, Slack, or Jira) a note is pointing at. */
export const SOURCE_LABELS: Record<LinkedSource, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

export interface NoteLink {
  source: LinkedSource;
  url: string;
  title: string;
}

export interface Note {
  id: string;
  title: string;
  body: string;
  tags: string[];
  links: NoteLink[];
  created_at: string;
  updated_at: string;
}

export interface NoteCreateInput {
  title: string;
  body?: string;
  tags?: string[];
  links?: NoteLink[];
}

export interface NoteUpdateInput {
  title?: string;
  body?: string;
  tags?: string[];
}

/** Builds the "annotate this" URL — `/notes`, pre-filled with a reference
 * to an existing item for the page to offer "new note" or "add to an
 * existing note" against. Shared by every page that links out to a real
 * GitHub/Slack/Jira item (Search, Archaeology, Who Should I Ask) via the
 * small `AnnotateLink` action, rather than each page building this query
 * string itself. */
export function annotateHref(source: LinkedSource, url: string, title: string): string {
  const params = new URLSearchParams({ linkSource: source, linkUrl: url, linkTitle: title });
  return `/notes?${params.toString()}`;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export async function fetchNotes(): Promise<Note[]> {
  return apiFetch<Note[]>("/v1/notes");
}

export async function createNote(input: NoteCreateInput): Promise<Note> {
  return apiFetch<Note>("/v1/notes", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
}

export async function updateNote(id: string, input: NoteUpdateInput): Promise<Note> {
  return apiFetch<Note>(`/v1/notes/${id}`, {
    method: "PATCH",
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
}

/** The "attach to an existing note" half of the annotate flow — the
 * other half is `createNote` seeding `links` at creation. */
export async function addLinkToNote(id: string, link: NoteLink): Promise<Note> {
  return apiFetch<Note>(`/v1/notes/${id}/links`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(link),
  });
}

/** By index, not by (source, url) — a note can in principle reference
 * the same item twice, and matching by content wouldn't unambiguously
 * say which one to drop. */
export async function removeLinkFromNote(id: string, linkIndex: number): Promise<Note> {
  return apiFetch<Note>(`/v1/notes/${id}/links/${linkIndex}`, { method: "DELETE" });
}

export async function deleteNote(id: string): Promise<void> {
  await apiFetch<void>(`/v1/notes/${id}`, { method: "DELETE" });
}

export async function deleteAllNotes(): Promise<number> {
  const result = await apiFetch<{ deleted_count: number }>("/v1/notes", { method: "DELETE" });
  return result.deleted_count;
}

/** Not routed through `apiFetch` — that helper always parses the response
 * as JSON, but this endpoint returns a raw Markdown document. Triggers a
 * real browser download rather than returning the text for the caller to
 * do something else with, since downloading is the only thing "export"
 * means here. */
export async function downloadNotesExport(): Promise<void> {
  const response = await fetch(`${API_URL}/v1/notes/export`, { credentials: "include" });
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "relay-notes.md";
  link.click();
  URL.revokeObjectURL(url);
}

"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type DirectoryEntry,
  type FileSearchMatch,
  type RepoOption,
  fetchDirectory,
  fetchRepos,
  searchFiles,
} from "@/lib/repoBrowser";

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 400) return "Connect GitHub on the Connections page first.";
    if (err.status === 401) return "Your session expired — sign in again.";
    return `Request failed (${err.status}).`;
  }
  return "Couldn't reach the server — check that the backend is running.";
}

export interface RepoFileSelection {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  targetType: "file" | "directory";
}

/** Repo list → breadcrumb directory browser → file select, built entirely
 * from editorial primitives. Shared by Archaeology and Who Should I Ask —
 * both feature routers expose an identical `/repos` + `/browse` pair
 * (ADR 0005: each feature owns its own surface, calling the same engine
 * module underneath), so this component takes the base path as a prop
 * rather than existing twice.
 *
 * `featureLabel` is optional, additive presentation only — when a caller
 * passes one (Archaeology passes `"Archaeology"`), the repo-browsing view
 * gains a small contextual label, a quieter "change repo" placement, and
 * "Whole repository"/"Files" section labels. When omitted (Who Should I
 * Ask doesn't pass it), the component renders exactly as it did before
 * this prop existed — this was a deliberate design pass scoped to
 * Archaeology only, not a shared redesign. */
export function RepoFilePicker({
  basePath,
  onSelect,
  featureLabel,
}: {
  basePath: string;
  onSelect: (selection: RepoFileSelection) => void;
  featureLabel?: string;
}) {
  const [repos, setRepos] = useState<RepoOption[] | "loading">("loading");
  const [repo, setRepo] = useState<RepoOption | null>(null);
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<DirectoryEntry[] | "loading">("loading");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);
  const [entriesError, setEntriesError] = useState<string | null>(null);

  // The ticket/PR-first entry point (ADR 0015) — a parallel path to the
  // repo-browse flow above, not a replacement. A search result already
  // carries its own repo, so picking a file from it looks up that repo's
  // `default_branch` from the already-fetched `repos` list rather than
  // requiring the user to browse to it first.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<FileSearchMatch[] | "loading" | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    fetchRepos(basePath)
      .then((r) => {
        setRepos(r);
        setReposError(null);
      })
      .catch((err: unknown) => {
        console.error(err);
        setReposError(describeError(err));
      });
  }, [basePath]);

  useEffect(() => {
    if (!repo) return;
    fetchDirectory(basePath, repo.owner, repo.name, path)
      .then((e) => {
        setEntries(e);
        setEntriesError(null);
      })
      .catch((err: unknown) => {
        console.error(err);
        setEntriesError(describeError(err));
      });
  }, [basePath, repo, path]);

  function changeRepo() {
    setRepo(null);
    setPath("");
    setSelectedPath(null);
  }

  function selectFile(entryPath: string) {
    if (!repo) return;
    setSelectedPath(entryPath);
    onSelect({
      owner: repo.owner,
      repo: repo.name,
      ref: repo.default_branch,
      path: entryPath,
      targetType: "file",
    });
  }

  function selectDirectory() {
    if (!repo) return;
    setSelectedPath(path || "/");
    onSelect({
      owner: repo.owner,
      repo: repo.name,
      ref: repo.default_branch,
      path,
      targetType: "directory",
    });
  }

  function enterDirectory(entryPath: string) {
    setEntries("loading");
    setPath(entryPath);
  }

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    setSearchResults("loading");
    setSearchError(null);
    try {
      setSearchResults(await searchFiles(basePath, q));
    } catch (err) {
      console.error(err);
      setSearchError(describeError(err));
      setSearchResults(null);
    }
  }

  function selectSearchFile(match: FileSearchMatch, filePath: string) {
    if (repos === "loading") return;
    const matchedRepo = repos.find((r) => r.full_name === match.repo);
    if (!matchedRepo) return;
    setSelectedPath(filePath);
    onSelect({
      owner: matchedRepo.owner,
      repo: matchedRepo.name,
      ref: matchedRepo.default_branch,
      path: filePath,
      targetType: "file",
    });
  }

  if (!repo) {
    return (
      <div>
        <SectionLabel tone="brand">Search a ticket, PR, or keyword</SectionLabel>
        <form onSubmit={runSearch} className="mt-3 flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="e.g. REL-42, or “retry logic”"
            className="border-line text-ink placeholder:text-muted focus:border-brand flex-1 border px-3 py-2 text-sm outline-none"
          />
          <button
            type="submit"
            className="border-brand text-brand hover:bg-brand hover:text-paper-white shrink-0 border px-3 py-2 text-xs font-medium tracking-[0.1em] uppercase transition-colors"
          >
            Search
          </button>
        </form>

        {searchError && <p className="text-brand mt-3 text-sm">{searchError}</p>}
        {searchResults === "loading" && <p className="text-muted mt-3 text-sm">Searching…</p>}
        {searchResults && searchResults !== "loading" && (
          <div className="mt-4">
            {searchResults.length === 0 ? (
              <p className="text-muted text-sm">No matching commits or pull requests.</p>
            ) : (
              <ul className="flex flex-col gap-4">
                {searchResults.map((match) => (
                  <li key={match.url}>
                    <a
                      href={match.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-brand text-sm font-medium text-ink transition-colors"
                    >
                      {match.kind === "pull_request" ? "PR" : "Commit"} · {match.title}
                    </a>
                    <p className="text-muted mt-0.5 text-xs">{match.repo}</p>
                    {match.files.length === 0 ? (
                      <p className="text-muted mt-1.5 text-xs italic">No files resolved.</p>
                    ) : (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {match.files.map((f) => (
                          <button
                            key={f}
                            type="button"
                            onClick={() => selectSearchFile(match, f)}
                            className={`border px-2 py-0.5 font-mono text-[11px] transition-colors ${
                              selectedPath === f
                                ? "border-brand text-brand"
                                : "border-line text-muted hover:border-brand hover:text-brand"
                            }`}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <Rule className="mt-8" />

        <SectionLabel tone="brand" className="mt-6">
          Repository
        </SectionLabel>
        <Rule className="mt-3" />
        {reposError ? (
          <p className="text-brand mt-6 text-sm">{reposError}</p>
        ) : repos === "loading" ? (
          <p className="text-muted mt-6 text-sm">Loading repositories…</p>
        ) : repos.length === 0 ? (
          <p className="text-muted mt-6 text-sm">
            No repositories found — connect GitHub first.
          </p>
        ) : (
          <ul>
            {repos.map((r) => (
              <li key={r.full_name} className="border-line border-b">
                <button
                  type="button"
                  onClick={() => {
                    setRepo(r);
                    setPath("");
                    setSelectedPath(null);
                    setEntries("loading");
                  }}
                  className="hover:text-brand w-full py-3 text-left text-sm font-medium text-ink transition-colors"
                >
                  {r.full_name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const crumbs = path ? path.split("/") : [];

  const breadcrumb = (
    <p className="text-muted text-xs">
      <button type="button" onClick={() => enterDirectory("")} className="hover:text-ink">
        root
      </button>
      {crumbs.map((crumb, i) => (
        <span key={i}>
          {" / "}
          <button
            type="button"
            onClick={() => enterDirectory(crumbs.slice(0, i + 1).join("/"))}
            className="hover:text-ink"
          >
            {crumb}
          </button>
        </span>
      ))}
    </p>
  );

  const changeRepoButton = (
    <button
      type="button"
      onClick={changeRepo}
      className="text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors"
    >
      {featureLabel ? "Change repo →" : "Change repo"}
    </button>
  );

  const analyzeButton = (
    <button
      type="button"
      onClick={selectDirectory}
      className="border-brand text-brand hover:bg-brand hover:text-paper-white border px-3 py-1.5 text-xs font-medium tracking-[0.1em] uppercase transition-colors"
    >
      Analyze {path ? "this folder" : featureLabel ? "entire repository" : "whole repo"} →
    </button>
  );

  return (
    <div>
      {featureLabel ? (
        <>
          <SectionLabel tone="muted" className="text-[10px] tracking-[0.25em]">
            {featureLabel} / {repo.name}
          </SectionLabel>
          <SectionLabel tone="brand" className="mt-2 truncate">
            {repo.full_name}
          </SectionLabel>
          <div className="mt-3 flex items-center justify-between gap-4">
            {breadcrumb}
            {changeRepoButton}
          </div>

          <SectionLabel tone="muted" className="mt-8">
            Whole repository
          </SectionLabel>
          <div className="mt-3">{analyzeButton}</div>

          <Rule className="mt-8" />

          <SectionLabel tone="muted" className="mt-6">
            Files
          </SectionLabel>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between gap-4">
            <SectionLabel tone="brand" className="truncate">
              {repo.full_name}
            </SectionLabel>
            {changeRepoButton}
          </div>
          <div className="mt-2">{breadcrumb}</div>
          <div className="mt-4">{analyzeButton}</div>
          <Rule className="mt-4" />
        </>
      )}

      {entriesError ? (
        <p className="text-brand mt-6 text-sm">{entriesError}</p>
      ) : entries === "loading" ? (
        <p className="text-muted mt-6 text-sm">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-muted mt-6 text-sm">Empty directory.</p>
      ) : (
        <ul className={featureLabel ? "mt-2" : ""}>
          {entries.map((entry) => (
            <li key={entry.path} className="border-line border-b">
              <button
                type="button"
                onClick={() =>
                  entry.type === "dir" ? enterDirectory(entry.path) : selectFile(entry.path)
                }
                className={`w-full py-3 text-left text-sm font-medium transition-colors ${
                  selectedPath === entry.path ? "text-brand" : "text-ink hover:text-brand"
                }`}
              >
                {entry.type === "dir" ? "▸ " : ""}
                {entry.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

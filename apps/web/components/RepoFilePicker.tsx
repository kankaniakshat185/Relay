"use client";

import { useEffect, useState } from "react";

import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import { type DirectoryEntry, type RepoOption, fetchDirectory, fetchRepos } from "@/lib/repoBrowser";

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
}

/** Repo list → breadcrumb directory browser → file select, built entirely
 * from editorial primitives. Shared by Archaeology and Who Should I Ask —
 * both feature routers expose an identical `/repos` + `/browse` pair
 * (ADR 0005: each feature owns its own surface, calling the same engine
 * module underneath), so this component takes the base path as a prop
 * rather than existing twice. */
export function RepoFilePicker({
  basePath,
  onSelect,
}: {
  basePath: string;
  onSelect: (selection: RepoFileSelection) => void;
}) {
  const [repos, setRepos] = useState<RepoOption[] | "loading">("loading");
  const [repo, setRepo] = useState<RepoOption | null>(null);
  const [path, setPath] = useState("");
  const [entries, setEntries] = useState<DirectoryEntry[] | "loading">("loading");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [reposError, setReposError] = useState<string | null>(null);
  const [entriesError, setEntriesError] = useState<string | null>(null);

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
    onSelect({ owner: repo.owner, repo: repo.name, ref: repo.default_branch, path: entryPath });
  }

  function enterDirectory(entryPath: string) {
    setEntries("loading");
    setPath(entryPath);
  }

  if (!repo) {
    return (
      <div>
        <SectionLabel tone="brand">Repository</SectionLabel>
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

  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <SectionLabel tone="brand" className="truncate">
          {repo.full_name}
        </SectionLabel>
        <button
          type="button"
          onClick={changeRepo}
          className="text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors"
        >
          Change repo
        </button>
      </div>

      <p className="text-muted mt-2 text-xs">
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

      <Rule className="mt-3" />

      {entriesError ? (
        <p className="text-brand mt-6 text-sm">{entriesError}</p>
      ) : entries === "loading" ? (
        <p className="text-muted mt-6 text-sm">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-muted mt-6 text-sm">Empty directory.</p>
      ) : (
        <ul>
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

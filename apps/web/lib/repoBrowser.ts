import { apiFetch } from "./api";

/**
 * Shared fetch layer for the repo/file picker both Archaeology and
 * Who Should I Ask use. Each feature exposes an identical pair of
 * `/repos` and `/browse` endpoints on its own router (not a shared
 * backend route) per ADR 0005 — this file is the frontend-only reuse of
 * that shape, taking the feature's base path as a parameter rather than
 * hardcoding one.
 */

export interface RepoOption {
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
}

export interface DirectoryEntry {
  name: string;
  path: string;
  type: "file" | "dir";
}

export async function fetchRepos(basePath: string): Promise<RepoOption[]> {
  return apiFetch<RepoOption[]>(`${basePath}/repos`);
}

export async function fetchDirectory(
  basePath: string,
  owner: string,
  repo: string,
  path: string
): Promise<DirectoryEntry[]> {
  const params = new URLSearchParams({ owner, repo, path });
  return apiFetch<DirectoryEntry[]>(`${basePath}/browse?${params.toString()}`);
}

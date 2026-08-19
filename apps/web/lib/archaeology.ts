import { apiFetch } from "./api";

export interface LineRange {
  start: number;
  end: number;
}

export interface PullRequestRef {
  number: number;
  title: string;
  url: string;
}

export interface RelatedSlackMessage {
  title: string;
  url: string;
  excerpt: string;
  occurred_at: string;
}

export interface CommitEntry {
  sha: string;
  short_sha: string;
  message: string;
  author: string | null;
  committed_at: string;
  url: string;
  line_ranges: LineRange[];
  pull_request: PullRequestRef | null;
  jira_ticket_key: string | null;
  jira_ticket_url: string | null;
  related_slack: RelatedSlackMessage[];
}

export interface ArchaeologyResponse {
  timeline: CommitEntry[];
}

export interface ArchaeologyRequest {
  owner: string;
  repo: string;
  ref: string;
  path: string;
}

export async function traceArchaeology(request: ArchaeologyRequest): Promise<ArchaeologyResponse> {
  return apiFetch<ArchaeologyResponse>("/v1/archaeology/trace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

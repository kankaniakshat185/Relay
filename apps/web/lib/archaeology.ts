import { apiFetch } from "./api";

export interface LineRange {
  start: number;
  end: number;
}

export interface PullRequestRef {
  number: number;
  title: string;
  url: string;
  has_unresolved_review: boolean;
}

export interface RelatedItem {
  source: "slack" | "jira";
  title: string;
  url: string;
  excerpt: string;
  occurred_at: string;
}

export interface ReviewComment {
  author: string | null;
  excerpt: string;
  url: string;
  occurred_at: string;
  state: string | null;
}

export interface CommitEntry {
  sha: string;
  short_sha: string;
  message: string;
  author: string | null;
  committed_at: string;
  url: string;
  line_ranges: LineRange[];
  files_touched: string[];
  pull_request: PullRequestRef | null;
  jira_ticket_key: string | null;
  jira_ticket_url: string | null;
  related_slack: RelatedItem[];
  similar_issues: RelatedItem[];
  review_comments: ReviewComment[];
}

export interface ArchaeologyResponse {
  timeline: CommitEntry[];
  files_total: number;
  files_analyzed: number;
  files_skipped: number;
}

export interface ArchaeologyRequest {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  target_type: "file" | "directory";
}

export async function traceArchaeology(request: ArchaeologyRequest): Promise<ArchaeologyResponse> {
  return apiFetch<ArchaeologyResponse>("/v1/archaeology/trace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

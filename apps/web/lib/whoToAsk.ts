import { apiFetch } from "./api";

export type RankingStrategy = "recency" | "frequency";

export interface CommitSummary {
  sha: string;
  short_sha: string;
  message: string;
  committed_at: string;
  url: string;
}

export interface RelatedItem {
  source: "slack" | "jira";
  title: string;
  url: string;
  excerpt: string;
  occurred_at: string;
}

export interface ReviewSummary {
  pr_number: number;
  pr_title: string;
  excerpt: string;
  url: string;
  occurred_at: string;
  state: string | null;
}

export interface PersonScore {
  author: string;
  score: number;
  touch_count: number;
  last_touch_at: string;
  /** Every commit backing this score, most recent first — not capped by
   * the API (they're already fetched); truncate for display client-side.
   * Empty for a review-only contributor — see `reviews`. */
  commits: CommitSummary[];
  /** This person's review commentary on PRs touching this file/directory
   * — kept separate from `commits` so a reviewer is never shown as
   * having committed code they only reviewed. */
  reviews: ReviewSummary[];
  jira_ticket_key: string | null;
  jira_ticket_url: string | null;
  related_slack: RelatedItem[];
  similar_issues: RelatedItem[];
}

export interface WhoToAskResponse {
  people: PersonScore[];
  strategy_used: RankingStrategy;
  files_total: number;
  files_analyzed: number;
  files_skipped: number;
}

export interface WhoToAskRequest {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  strategy: RankingStrategy;
  target_type: "file" | "directory" | "pull_request";
  /** Required when `target_type` is `"pull_request"`. */
  pr_number?: number;
}

export async function rankWhoToAsk(request: WhoToAskRequest): Promise<WhoToAskResponse> {
  return apiFetch<WhoToAskResponse>("/v1/who-to-ask/rank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

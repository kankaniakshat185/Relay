import { apiFetch } from "./api";

export interface RelatedItem {
  source: "slack" | "jira" | "github";
  title: string;
  url: string;
  excerpt: string;
  occurred_at: string;
}

export interface FlaggedPullRequest {
  number: number;
  title: string;
  url: string;
  author: string | null;
  author_inactive: boolean;
  discussion: RelatedItem[];
}

export interface DecisionDebtResponse {
  flagged: FlaggedPullRequest[];
  prs_scanned: number;
  decision_docs_found: number;
}

export interface DecisionDebtOptions {
  owner: string;
  repo: string;
  minDiscussionItems?: number;
  inactiveAfterDays?: number;
}

export async function scanDecisionDebt(
  options: DecisionDebtOptions
): Promise<DecisionDebtResponse> {
  return apiFetch<DecisionDebtResponse>("/v1/decision-debt/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      owner: options.owner,
      repo: options.repo,
      min_discussion_items: options.minDiscussionItems ?? 2,
      inactive_after_days: options.inactiveAfterDays ?? 180,
    }),
  });
}

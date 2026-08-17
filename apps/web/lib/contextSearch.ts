import { apiFetch } from "./api";

export interface SourceCitation {
  source: "github" | "slack" | "jira";
  source_type: "pull_request" | "commit" | "message" | "issue";
  title: string;
  url: string;
  author: string | null;
  occurred_at: string;
}

export interface ContextSearchResponse {
  answer: string;
  sources: SourceCitation[];
}

export async function runContextSearch(query: string): Promise<ContextSearchResponse> {
  return apiFetch<ContextSearchResponse>("/v1/context-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

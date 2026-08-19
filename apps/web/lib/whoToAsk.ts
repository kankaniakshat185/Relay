import { apiFetch } from "./api";

export type RankingStrategy = "recency" | "frequency";

export interface PersonScore {
  author: string;
  score: number;
  touch_count: number;
  last_touch_at: string;
  sample_commit_urls: string[];
}

export interface WhoToAskResponse {
  people: PersonScore[];
  strategy_used: RankingStrategy;
}

export interface WhoToAskRequest {
  owner: string;
  repo: string;
  ref: string;
  path: string;
  strategy: RankingStrategy;
}

export async function rankWhoToAsk(request: WhoToAskRequest): Promise<WhoToAskResponse> {
  return apiFetch<WhoToAskResponse>("/v1/who-to-ask/rank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}

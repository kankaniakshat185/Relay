import { apiFetch } from "./api";
import type { ItemCitation, LlmProvider, LlmUnavailableReason } from "./synthesis";

export type { LlmProvider, LlmUnavailableReason };
export { LLM_PROVIDERS } from "./synthesis";

export type SourceCitation = ItemCitation;

export interface ContextSearchResponse {
  used_llm: boolean;
  llm_unavailable_reason: LlmUnavailableReason | null;
  answer: string | null;
  sources: SourceCitation[];
}

export interface ContextSearchOptions {
  useLlm?: boolean;
  llmProvider?: LlmProvider;
  apiKey?: string;
}

export async function runContextSearch(
  query: string,
  options: ContextSearchOptions = {}
): Promise<ContextSearchResponse> {
  return apiFetch<ContextSearchResponse>("/v1/context-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      use_llm: options.useLlm ?? false,
      llm_provider: options.llmProvider ?? "openai",
      api_key: options.apiKey || null,
    }),
  });
}

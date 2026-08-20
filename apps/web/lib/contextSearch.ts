import { apiFetch } from "./api";

export type LlmProvider = "openai" | "groq" | "anthropic" | "gemini";

export const LLM_PROVIDERS: { id: LlmProvider; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "groq", label: "Groq" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Gemini" },
];

export interface SourceCitation {
  source: "github" | "slack" | "jira" | "notes";
  source_type: "pull_request" | "commit" | "message" | "issue" | "review_comment" | "note";
  title: string;
  url: string;
  author: string | null;
  occurred_at: string;
  excerpt: string;
}

export type LlmUnavailableReason =
  | "rate_limited"
  | "api_key_required"
  | "invalid_api_key"
  | "provider_error";

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

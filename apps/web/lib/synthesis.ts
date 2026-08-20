/** Shared with the backend's own `engine/synthesis` extraction — these
 * types and the provider list aren't specific to Context Search, only to
 * "ask an LLM to answer/summarize over some retrieved items," so Weekly
 * Digest reuses them directly instead of redefining its own copy. */

export type LlmProvider = "openai" | "groq" | "anthropic" | "gemini";

export const LLM_PROVIDERS: { id: LlmProvider; label: string }[] = [
  { id: "openai", label: "OpenAI" },
  { id: "groq", label: "Groq" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Gemini" },
];

export type LlmUnavailableReason =
  | "rate_limited"
  | "api_key_required"
  | "invalid_api_key"
  | "provider_error";

export const UNAVAILABLE_MESSAGES: Record<LlmUnavailableReason, string> = {
  rate_limited:
    "Free tier limit reached for today — bring your own API key above, or try again tomorrow.",
  api_key_required: "This provider has no free tier — add your own API key above to use it.",
  invalid_api_key: "That API key was rejected — double-check it and try again.",
  provider_error: "The provider had a hiccup — try again in a moment.",
};

export interface ItemCitation {
  source: "github" | "slack" | "jira" | "notes";
  source_type: "pull_request" | "commit" | "message" | "issue" | "review_comment" | "note";
  title: string;
  url: string;
  author: string | null;
  occurred_at: string;
  excerpt: string;
}

import { LLM_PROVIDERS, type LlmProvider } from "@/lib/synthesis";

import { SectionLabel } from "./SectionLabel";

/** The "which model, which key" row — shared by Search and Weekly Digest,
 * the two features that offer an optional LLM synthesis step on top of
 * raw retrieval (ADR 0008). Collapses to zero height (not just hidden)
 * when `visible` is false, so raw mode stays exactly as clean as if this
 * row didn't exist — see the Context Search page this was lifted from. */
export function LlmProviderPicker({
  visible,
  provider,
  onProviderChange,
  apiKey,
  onApiKeyChange,
}: {
  visible: boolean;
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
  apiKey: string;
  onApiKeyChange: (apiKey: string) => void;
}) {
  const selected = LLM_PROVIDERS.find((p) => p.id === provider);

  return (
    <div
      className={`overflow-hidden transition-all duration-200 ease-out ${
        visible ? "mt-5 max-h-40 opacity-100" : "mt-0 max-h-0 opacity-0"
      }`}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <SectionLabel tone="brand">Model</SectionLabel>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {LLM_PROVIDERS.map((p) => (
            <button
              key={p.id}
              type="button"
              aria-pressed={provider === p.id}
              onClick={() => onProviderChange(p.id)}
              className={`pb-0.5 text-sm font-medium transition-colors ${
                provider === p.id
                  ? "decoration-brand text-ink underline decoration-2 underline-offset-4"
                  : "text-muted hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 max-w-lg">
        <label htmlFor="llm-api-key" className="sr-only">
          API key for {selected?.label}
        </label>
        <input
          id="llm-api-key"
          type="password"
          value={apiKey}
          onChange={(e) => onApiKeyChange(e.target.value)}
          placeholder={
            provider === "openai"
              ? "Your OpenAI API key — optional, uses Relay's free tier if left blank"
              : `Your ${selected?.label} API key — required, no free tier for this provider`
          }
          className="border-line focus:border-ink w-full border-b bg-transparent py-2 text-sm outline-none"
        />
      </div>
    </div>
  );
}

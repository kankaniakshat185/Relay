"use client";

import Link from "next/link";
import { useState } from "react";

import { AnnotateLink } from "@/components/editorial/AnnotateLink";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { RedPanel } from "@/components/editorial/RedPanel";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type ContextSearchResponse,
  type LlmProvider,
  type SourceCitation,
  LLM_PROVIDERS,
  runContextSearch,
} from "@/lib/contextSearch";

const SOURCE_ORDER = ["github", "slack", "jira", "notes"] as const;
const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
  notes: "Notes",
};

const UNAVAILABLE_MESSAGES: Record<string, string> = {
  rate_limited:
    "Free tier limit reached for today — bring your own API key above, or try again tomorrow.",
  api_key_required: "This provider has no free tier — add your own API key above to use it.",
  invalid_api_key: "That API key was rejected — double-check it and try again.",
  provider_error: "The provider had a hiccup — try again in a moment.",
};

function groupBySource(
  sources: SourceCitation[]
): [SourceCitation["source"], SourceCitation[]][] {
  const groups = new Map<SourceCitation["source"], SourceCitation[]>();
  for (const source of sources) {
    groups.set(source.source, [...(groups.get(source.source) ?? []), source]);
  }
  return SOURCE_ORDER.filter((source) => groups.has(source)).map((source) => [
    source,
    groups.get(source)!,
  ]);
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [provider, setProvider] = useState<LlmProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [result, setResult] = useState<ContextSearchResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setStatus("loading");
    setSubmittedQuery(query);
    try {
      const response = await runContextSearch(query, { useLlm, llmProvider: provider, apiKey });
      setResult(response);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      console.error(err instanceof ApiError ? err.message : err);
    }
  }

  return (
    <div>
      <SectionLabel tone="brand">Context Search</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Ask Relay
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Searches your connected GitHub, Slack, and Jira activity and returns the relevant
        context directly — with an optional AI summary on top.
      </p>

      {/* Primary decision: what kind of answer. Stays the one thing with
          this visual weight — the provider/key row below is deliberately
          quieter, see the collapsing container underneath. */}
      <div className="mt-8 border-line flex w-fit border">
        <button
          type="button"
          aria-pressed={!useLlm}
          onClick={() => setUseLlm(false)}
          className={`px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
            !useLlm ? "bg-ink text-paper" : "text-muted hover:text-ink"
          }`}
        >
          Raw
        </button>
        <button
          type="button"
          aria-pressed={useLlm}
          onClick={() => setUseLlm(true)}
          className={`border-line border-l px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
            useLlm ? "bg-brand text-paper-white" : "text-muted hover:text-ink"
          }`}
        >
          AI Summary
        </button>
      </div>

      {/* Secondary decision: which model. Quiet editorial metadata row,
          not a second segmented control — collapses to zero height (not
          just hidden) so raw mode stays exactly as clean as before. */}
      <div
        className={`overflow-hidden transition-all duration-200 ease-out ${
          useLlm ? "mt-5 max-h-40 opacity-100" : "mt-0 max-h-0 opacity-0"
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
                onClick={() => setProvider(p.id)}
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
            API key for {LLM_PROVIDERS.find((p) => p.id === provider)?.label}
          </label>
          <input
            id="llm-api-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              provider === "openai"
                ? "Your OpenAI API key — optional, uses Relay's free tier if left blank"
                : `Your ${LLM_PROVIDERS.find((p) => p.id === provider)?.label} API key — required, no free tier for this provider`
            }
            className="border-line focus:border-ink w-full border-b bg-transparent py-2 text-sm outline-none"
          />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-8 md:grid md:grid-cols-12">
        <div className="border-ink flex items-end gap-4 border-b pb-3 md:col-span-10">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Why is there retry logic in the payment handler?"
            className="placeholder:text-line w-full bg-transparent text-lg outline-none sm:text-2xl"
          />
          <button
            type="submit"
            disabled={status === "loading"}
            aria-label="Search"
            className="bg-brand text-paper-white hover:bg-ink hover:text-paper flex h-10 w-10 shrink-0 items-center justify-center text-lg transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "…" : "↗"}
          </button>
        </div>
      </form>

      {status === "error" && (
        <p className="text-muted mt-8 text-sm">
          Something went wrong running that search — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-20">
          <SectionLabel>Question</SectionLabel>
          <p className="font-serif mt-3 max-w-2xl text-2xl text-ink sm:text-3xl">
            {submittedQuery}
          </p>

          {useLlm &&
            (result.used_llm && result.answer ? (
              <RedPanel className="mt-10 p-6 sm:p-8">
                <p className="text-sm leading-relaxed whitespace-pre-wrap sm:text-base">
                  {result.answer}
                </p>
              </RedPanel>
            ) : result.llm_unavailable_reason ? (
              <div className="border-brand mt-10 border p-6 sm:p-8">
                <SectionLabel tone="brand">AI summary unavailable</SectionLabel>
                <p className="text-muted mt-3 text-sm leading-relaxed">
                  {UNAVAILABLE_MESSAGES[result.llm_unavailable_reason]}
                </p>
              </div>
            ) : null)}

          {result.sources.length === 0 ? (
            <p className="text-muted mt-10 text-sm">
              No connected data yet to search — connect GitHub, Slack, or Jira first.
            </p>
          ) : (
            groupBySource(result.sources).map(([source, items]) => (
              <div key={source} className="mt-16">
                <div className="flex items-baseline gap-4">
                  <SectionLabel tone="ink" className="text-base tracking-[0.15em]">
                    {SOURCE_LABELS[source] ?? source}
                  </SectionLabel>
                  <Rule className="flex-1" />
                </div>

                <ul className="mt-6 flex flex-col gap-6">
                  {items.map((item) => (
                    <li key={item.url}>
                      <div className="flex items-baseline justify-between gap-4">
                        {source === "notes" ? (
                          <Link
                            href={item.url}
                            className="hover:text-brand text-base font-medium text-ink transition-colors"
                          >
                            {item.title}
                          </Link>
                        ) : (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:text-brand text-base font-medium text-ink transition-colors"
                          >
                            {item.title}
                          </a>
                        )}
                        {source !== "notes" && (
                          <AnnotateLink source={source} url={item.url} title={item.title} />
                        )}
                      </div>
                      <p className="text-muted mt-1 text-sm leading-relaxed">{item.excerpt}</p>
                      <Metadata
                        items={[
                          item.source_type,
                          item.author,
                          new Date(item.occurred_at).toLocaleDateString(),
                        ]}
                        className="mt-1"
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

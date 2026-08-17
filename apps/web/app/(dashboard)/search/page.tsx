"use client";

import { useState } from "react";

import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { RedPanel } from "@/components/editorial/RedPanel";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type ContextSearchResponse,
  type SourceCitation,
  runContextSearch,
} from "@/lib/contextSearch";

const SOURCE_ORDER = ["github", "slack", "jira"] as const;
const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

function groupBySource(sources: SourceCitation[]): [string, SourceCitation[]][] {
  const groups = new Map<string, SourceCitation[]>();
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
  const [result, setResult] = useState<ContextSearchResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setStatus("loading");
    setSubmittedQuery(query);
    try {
      const response = await runContextSearch(query);
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
      <p className="text-muted mt-4 max-w-md text-sm leading-relaxed">
        Searches your connected GitHub, Slack, and Jira activity and returns one synthesized,
        source-attributed answer.
      </p>

      <form onSubmit={handleSubmit} className="mt-16 md:grid md:grid-cols-12">
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
            className="bg-brand text-paper-white hover:bg-ink flex h-10 w-10 shrink-0 items-center justify-center text-lg transition-colors disabled:opacity-50"
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

          <RedPanel className="mt-10 p-6 sm:p-8">
            <p className="text-sm leading-relaxed whitespace-pre-wrap sm:text-base">
              {result.answer}
            </p>
          </RedPanel>

          {groupBySource(result.sources).map(([source, items]) => (
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
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-brand text-base font-medium text-ink transition-colors"
                    >
                      {item.title}
                    </a>
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
          ))}
        </div>
      )}
    </div>
  );
}

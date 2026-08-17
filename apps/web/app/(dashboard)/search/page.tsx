"use client";

import { useState } from "react";

import { ApiError } from "@/lib/api";
import { type ContextSearchResponse, runContextSearch } from "@/lib/contextSearch";

const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<ContextSearchResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setStatus("loading");
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
    <div className="max-w-3xl">
      <p className="text-xs tracking-[0.2em] text-neutral-400 uppercase">Context Search</p>
      <h1 className="font-serif mt-2 text-4xl text-neutral-900">Ask Relay</h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-neutral-600">
        Searches your connected GitHub, Slack, and Jira activity and returns one synthesized,
        source-attributed answer.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 flex gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. why is there retry logic in the payment handler?"
          className="focus:border-brand h-12 flex-1 rounded-md border border-neutral-300 px-4 text-sm outline-none"
        />
        <button
          type="submit"
          disabled={status === "loading"}
          className="bg-brand text-brand-foreground h-12 rounded-md px-6 text-sm font-medium disabled:opacity-50"
        >
          {status === "loading" ? "Searching…" : "Search"}
        </button>
      </form>

      {status === "error" && (
        <p className="mt-6 text-sm text-neutral-500">
          Something went wrong running that search — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-10 space-y-8">
          <div className="bg-brand text-brand-foreground rounded-md p-6">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.answer}</p>
          </div>

          {result.sources.length > 0 && (
            <div>
              <p className="text-xs tracking-[0.2em] text-neutral-400 uppercase">Sources</p>
              <ul className="mt-3 divide-y divide-neutral-200 rounded-md border border-neutral-200">
                {result.sources.map((source) => (
                  <li key={source.url} className="p-4">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-brand text-sm font-medium text-neutral-900"
                    >
                      {source.title}
                    </a>
                    <p className="mt-1 text-xs text-neutral-500">
                      {SOURCE_LABELS[source.source] ?? source.source} · {source.source_type}
                      {source.author ? ` · ${source.author}` : ""} ·{" "}
                      {new Date(source.occurred_at).toLocaleDateString()}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

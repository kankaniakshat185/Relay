"use client";

import { useState } from "react";

import { RepoFilePicker, type RepoFileSelection } from "@/components/RepoFilePicker";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import { type RankingStrategy, type WhoToAskResponse, rankWhoToAsk } from "@/lib/whoToAsk";

export default function WhoToAskPage() {
  const [selection, setSelection] = useState<RepoFileSelection | null>(null);
  const [strategy, setStrategy] = useState<RankingStrategy>("recency");
  const [result, setResult] = useState<WhoToAskResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function runRank(next: RepoFileSelection, nextStrategy: RankingStrategy) {
    setStatus("loading");
    setResult(null);
    try {
      const response = await rankWhoToAsk({ ...next, strategy: nextStrategy });
      setResult(response);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      console.error(err instanceof ApiError ? err.message : err);
    }
  }

  function handleSelect(next: RepoFileSelection) {
    setSelection(next);
    runRank(next, strategy);
  }

  function handleStrategyChange(next: RankingStrategy) {
    setStrategy(next);
    if (selection) runRank(selection, next);
  }

  const topScore = result?.people[0]?.score ?? 0;

  return (
    <div>
      <SectionLabel tone="brand">Who Should I Ask</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Find the right person
      </DisplayHeading>
      <p className="text-muted mt-4 max-w-md text-sm leading-relaxed">
        Pick a file. Relay ranks everyone who&apos;s touched it — by how recently, or how often —
        using its git blame history.
      </p>

      <div className="mt-8 border-line flex w-fit border">
        {(["recency", "frequency"] as const).map((s, i) => (
          <button
            key={s}
            type="button"
            aria-pressed={strategy === s}
            onClick={() => handleStrategyChange(s)}
            className={`px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
              i === 1 ? "border-line border-l" : ""
            } ${strategy === s ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
          >
            {s === "recency" ? "Recently active" : "Most involved"}
          </button>
        ))}
      </div>

      <Rule className="mt-8" />

      <div className="mt-8 max-w-lg">
        <RepoFilePicker basePath="/v1/who-to-ask" onSelect={handleSelect} />
      </div>

      {status === "loading" && (
        <p className="text-muted mt-12 text-sm">Ranking {selection?.path}…</p>
      )}

      {status === "error" && (
        <p className="text-muted mt-12 text-sm">
          Something went wrong ranking that file — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-20">
          <SectionLabel>{selection?.path}</SectionLabel>

          {result.people.length === 0 ? (
            <p className="text-muted mt-6 text-sm">No blame history for this file.</p>
          ) : (
            <ul className="mt-6 flex flex-col gap-10">
              {result.people.map((person, i) => (
                <li key={person.author}>
                  <div className="flex items-baseline justify-between gap-4">
                    <p className="font-serif text-xl text-ink sm:text-2xl">{person.author}</p>
                    <span className="text-muted text-xs tracking-[0.1em] uppercase">
                      #{i + 1}
                    </span>
                  </div>
                  <div className="border-line mt-3 h-1.5 w-full border">
                    <div
                      className="bg-brand h-full"
                      style={{ width: `${Math.max((person.score / topScore) * 100, 4)}%` }}
                    />
                  </div>
                  <Metadata
                    items={[
                      `${person.touch_count} commit${person.touch_count === 1 ? "" : "s"}`,
                      `Last active ${new Date(person.last_touch_at).toLocaleDateString()}`,
                    ]}
                    className="mt-3"
                  />
                  <div className="mt-2 flex flex-wrap gap-x-4">
                    {person.sample_commit_urls.map((url) => (
                      <a
                        key={url}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-brand text-xs text-muted transition-colors"
                      >
                        view commit ↗
                      </a>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";

import { AnnotateLink } from "@/components/editorial/AnnotateLink";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { LlmProviderPicker } from "@/components/editorial/LlmProviderPicker";
import { Metadata } from "@/components/editorial/Metadata";
import { RedPanel } from "@/components/editorial/RedPanel";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type ItemCitation,
  type LlmProvider,
  UNAVAILABLE_MESSAGES,
} from "@/lib/synthesis";
import {
  type ParsedDigestSections,
  type WeeklyDigestResponse,
  parseDigestSections,
  runWeeklyDigest,
} from "@/lib/weeklyDigest";

const SOURCE_ORDER = ["github", "slack", "jira", "notes"] as const;
const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
  notes: "Notes",
};

const PERIODS = [
  { days: 7, label: "7 days" },
  { days: 14, label: "14 days" },
  { days: 30, label: "30 days" },
] as const;

function groupBySource(
  sources: ItemCitation[],
): [ItemCitation["source"], ItemCitation[]][] {
  const groups = new Map<ItemCitation["source"], ItemCitation[]>();
  for (const source of sources) {
    groups.set(source.source, [...(groups.get(source.source) ?? []), source]);
  }
  return SOURCE_ORDER.filter((source) => groups.has(source)).map((source) => [
    source,
    groups.get(source)!,
  ]);
}

/** "Aug 14–20", or "Aug 28 – Sep 3" across a month boundary — presentation
 * only, computed from when the request was actually submitted, not the
 * live (possibly since-edited) controls. */
function formatDateRange(end: Date, days: number): string {
  const start = new Date(end);
  start.setDate(start.getDate() - days);
  const sameMonth =
    start.getMonth() === end.getMonth() &&
    start.getFullYear() === end.getFullYear();
  const startLabel = start.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const endLabel = sameMonth
    ? `${end.getDate()}`
    : end.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return `${startLabel}–${endLabel}`;
}

export default function WeeklyDigestPage() {
  const [days, setDays] = useState(7);
  const [useLlm, setUseLlm] = useState(false);
  const [provider, setProvider] = useState<LlmProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [result, setResult] = useState<WeeklyDigestResponse | null>(null);
  const [submittedDays, setSubmittedDays] = useState<number | null>(null);
  const [submittedUseLlm, setSubmittedUseLlm] = useState(false);
  const [submittedAt, setSubmittedAt] = useState<Date | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  // Once a digest exists, the configuration strip collapses into a
  // one-line summary — the page reads as a finished editorial document,
  // not a settings form sitting above its own result. "Regenerate" brings
  // the strip back without discarding the digest still on screen.
  const [configOpen, setConfigOpen] = useState(true);

  async function handleGenerate() {
    setStatus("loading");
    const generatedAt = new Date();
    try {
      const response = await runWeeklyDigest({
        days,
        useLlm,
        llmProvider: provider,
        apiKey,
      });
      setResult(response);
      setSubmittedDays(days);
      setSubmittedUseLlm(useLlm);
      setSubmittedAt(generatedAt);
      setConfigOpen(false);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      console.error(err instanceof ApiError ? err.message : err);
    }
  }

  const parsedSections: ParsedDigestSections | null =
    result?.used_llm && result.digest
      ? parseDigestSections(result.digest)
      : null;

  return (
    <div>
      <SectionLabel tone="brand">Weekly Digest</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        What happened?
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Everything across your connected GitHub, Slack, Jira, and Notes in a
        recent window — what shipped, what is still being discussed, and what
        looks unresolved.
      </p>

      <Rule className="mt-16" />

      {configOpen ? (
        <div className="mt-8 flex flex-col gap-6 sm:max-w-[496px]">
          {/* Window */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
              Window
            </SectionLabel>
            <div className="border-line flex w-full border sm:w-[420px]">
              {PERIODS.map((period, i) => (
                <button
                  key={period.days}
                  type="button"
                  aria-pressed={days === period.days}
                  onClick={() => setDays(period.days)}
                  className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                    i > 0 ? "border-line border-l" : ""
                  } ${days === period.days ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </div>

          {/* View, with Model (only once AI Summary is actually chosen)
              attached directly beneath it — one unit, so the gap below it
              to the button stays the same whether Model is showing or not. */}
          <div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
              <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
                View
              </SectionLabel>
              <div className="border-line flex w-full border sm:w-[420px]">
                <button
                  type="button"
                  aria-pressed={!useLlm}
                  onClick={() => setUseLlm(false)}
                  className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                    !useLlm ? "bg-ink text-paper" : "text-muted hover:text-ink"
                  }`}
                >
                  Raw
                </button>
                <button
                  type="button"
                  aria-pressed={useLlm}
                  onClick={() => setUseLlm(true)}
                  className={`border-line border-l flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                    useLlm ? "bg-ink text-paper" : "text-muted hover:text-ink"
                  }`}
                >
                  AI Summary
                </button>
              </div>
            </div>

            <LlmProviderPicker
              visible={useLlm}
              provider={provider}
              onProviderChange={setProvider}
              apiKey={apiKey}
              onApiKeyChange={setApiKey}
            />
          </div>

          {/* Generate — always the last row, whether Model is showing or
              not, so it never lands between View and Model. */}
          <button
            type="button"
            onClick={handleGenerate}
            disabled={status === "loading"}
            className="bg-brand text-paper-white hover:bg-ink hover:text-paper self-end px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "Generating…" : "Generate Digest →"}
          </button>
        </div>
      ) : (
        <div className="mt-8 flex items-baseline justify-between gap-4">
          <Metadata
            items={[
              submittedDays !== null ? `${submittedDays} days` : null,
              submittedUseLlm ? "AI summary" : "Raw",
              submittedAt && submittedDays !== null
                ? formatDateRange(submittedAt, submittedDays)
                : null,
            ]}
          />
          <button
            type="button"
            onClick={() => setConfigOpen(true)}
            className="text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors"
          >
            Regenerate →
          </button>
        </div>
      )}

      {status === "error" && (
        <p className="text-muted mt-8 text-sm">
          Something went wrong generating that digest — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-16">
          {submittedUseLlm &&
            (result.used_llm && result.digest ? (
              parsedSections ? (
                <div className="flex flex-col gap-12">
                  <DigestSection
                    label="Shipped"
                    sub="What changed this week"
                    text={parsedSections.shipped}
                  />
                  <DigestSection
                    label="Still in Motion"
                    sub="Work that is still being discussed"
                    text={parsedSections.stillInMotion}
                  />
                  <DigestSection
                    label="Unresolved"
                    sub="Things that may need attention"
                    text={parsedSections.unresolved}
                  />
                </div>
              ) : (
                <RedPanel className="p-6 sm:p-8">
                  <p className="text-sm leading-relaxed whitespace-pre-wrap sm:text-base">
                    {result.digest}
                  </p>
                </RedPanel>
              )
            ) : result.llm_unavailable_reason ? (
              <div className="border-brand border p-6 sm:p-8">
                <SectionLabel tone="brand">AI summary unavailable</SectionLabel>
                <p className="text-muted mt-3 text-sm leading-relaxed">
                  {UNAVAILABLE_MESSAGES[result.llm_unavailable_reason]}
                </p>
              </div>
            ) : null)}

          {result.sources.length === 0 ? (
            <p className="text-muted mt-10 text-sm">
              Nothing in that window — connect GitHub, Slack, or Jira, or widen
              the period.
            </p>
          ) : (
            groupBySource(result.sources).map(([source, items]) => (
              <div key={source} className="mt-16">
                <div className="flex items-baseline gap-4">
                  <SectionLabel
                    tone="ink"
                    className="text-base tracking-[0.15em]"
                  >
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
                          <AnnotateLink
                            source={source}
                            url={item.url}
                            title={item.title}
                          />
                        )}
                      </div>
                      <p className="text-muted mt-1 text-sm leading-relaxed">
                        {item.excerpt}
                      </p>
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

/** One third of the generated narrative — "Shipped", "Still in Motion",
 * "Unresolved" — styled like Flaky Tests' own workflow header (a
 * SectionLabel + full-width Rule, then a serif sub-line) so a generated
 * digest reads as the same kind of editorial content as the rest of
 * Relay, not a distinct "AI output" block. */
function DigestSection({
  label,
  sub,
  text,
}: {
  label: string;
  sub: string;
  text: string;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-4">
        <SectionLabel tone="brand" className="text-base tracking-[0.15em]">
          {label}
        </SectionLabel>
        <Rule className="flex-1" />
      </div>
      <p className="font-serif text-ink mt-4 text-xl sm:text-2xl">{sub}</p>
      <p className="text-muted mt-3 max-w-2xl text-sm leading-relaxed whitespace-pre-wrap sm:text-base">
        {text}
      </p>
    </div>
  );
}

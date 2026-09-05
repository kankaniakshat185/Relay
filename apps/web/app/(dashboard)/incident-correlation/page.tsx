"use client";

import { useState } from "react";

import { RepoFilePicker, type RepoFileSelection } from "@/components/RepoFilePicker";
import type { CommitEntry } from "@/lib/archaeology";
import { AnnotateLink } from "@/components/editorial/AnnotateLink";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { LlmProviderPicker } from "@/components/editorial/LlmProviderPicker";
import { Metadata } from "@/components/editorial/Metadata";
import { RedPanel } from "@/components/editorial/RedPanel";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type IncidentCorrelationResponse,
  runIncidentCorrelation,
} from "@/lib/incidentCorrelation";
import { type ItemCitation, type LlmProvider, UNAVAILABLE_MESSAGES } from "@/lib/synthesis";

const SOURCE_ORDER = ["github", "slack", "jira", "notes"] as const;
const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  slack: "Slack",
  jira: "Jira",
  notes: "Notes",
};

const WINDOWS = [
  { hours: 24, label: "24h" },
  { hours: 48, label: "48h" },
  { hours: 72, label: "72h" },
] as const;

function groupBySource(sources: ItemCitation[]): [ItemCitation["source"], ItemCitation[]][] {
  const groups = new Map<ItemCitation["source"], ItemCitation[]>();
  for (const source of sources) {
    groups.set(source.source, [...(groups.get(source.source) ?? []), source]);
  }
  return SOURCE_ORDER.filter((source) => groups.has(source)).map((source) => [
    source,
    groups.get(source)!,
  ]);
}

export default function IncidentCorrelationPage() {
  const [incidentAtLocal, setIncidentAtLocal] = useState("");
  const [windowBeforeHours, setWindowBeforeHours] = useState<number>(48);
  const [useLlm, setUseLlm] = useState(false);
  const [provider, setProvider] = useState<LlmProvider>("openai");
  const [apiKey, setApiKey] = useState("");
  const [traceFile, setTraceFile] = useState(false);
  const [selection, setSelection] = useState<RepoFileSelection | null>(null);

  const [result, setResult] = useState<IncidentCorrelationResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [configOpen, setConfigOpen] = useState(true);

  const canSubmit = incidentAtLocal !== "" && (!traceFile || selection !== null);

  async function handleCorrelate() {
    if (!canSubmit) return;
    setStatus("loading");
    try {
      const response = await runIncidentCorrelation({
        incidentAt: new Date(incidentAtLocal).toISOString(),
        windowBeforeHours,
        useLlm,
        llmProvider: provider,
        apiKey,
        owner: traceFile ? selection?.owner : undefined,
        repo: traceFile ? selection?.repo : undefined,
        ref: traceFile ? selection?.ref : undefined,
        filePath: traceFile ? selection?.path : undefined,
      });
      setResult(response);
      setConfigOpen(false);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      console.error(err instanceof ApiError ? err.message : err);
    }
  }

  function handleFileSelect(next: RepoFileSelection) {
    // Only a single file's own blame history is a meaningful thing to
    // filter to an incident window — a directory or a PR pools many
    // files/commits, which is what v1's plain time-window view already
    // covers without narrowing to one path.
    if (next.targetType !== "file") return;
    setSelection(next);
  }

  return (
    <div>
      <SectionLabel tone="brand">Incident Correlation</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        What changed before this broke?
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Give Relay a time an incident was noticed. It surfaces everything
        across your connected GitHub, Slack, Jira, and Notes around that
        window — and, if you name a file, that file&rsquo;s own commit history
        filtered to the same window.
      </p>

      <Rule className="mt-16" />

      {configOpen ? (
        <div className="mt-8 flex flex-col gap-6 sm:max-w-[496px]">
          {/* Incident time */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
              When
            </SectionLabel>
            <input
              type="datetime-local"
              value={incidentAtLocal}
              onChange={(e) => setIncidentAtLocal(e.target.value)}
              className="border-line text-ink w-full border bg-transparent px-4 py-2 text-sm sm:w-[420px]"
            />
          </div>

          {/* Window before the incident */}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
              Window
            </SectionLabel>
            <div className="border-line flex w-full border sm:w-[420px]">
              {WINDOWS.map((w, i) => (
                <button
                  key={w.hours}
                  type="button"
                  aria-pressed={windowBeforeHours === w.hours}
                  onClick={() => setWindowBeforeHours(w.hours)}
                  className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                    i > 0 ? "border-line border-l" : ""
                  } ${
                    windowBeforeHours === w.hours
                      ? "bg-ink text-paper"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {w.label} before
                </button>
              ))}
            </div>
          </div>

          {/* View, with Model attached beneath — same reasoning as
              Weekly Digest: the Generate button always lands after both,
              never between them. */}
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
                  AI Narrative
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

          {/* Optional file trace (v2) */}
          <div>
            <button
              type="button"
              onClick={() => {
                setTraceFile((v) => !v);
                setSelection(null);
              }}
              className="text-muted hover:text-ink text-xs font-medium tracking-[0.15em] uppercase transition-colors"
            >
              {traceFile ? "− Remove file" : "+ Narrow to a file"}
            </button>

            {traceFile && (
              <div className="mt-4">
                <RepoFilePicker
                  basePath="/v1/archaeology"
                  onSelect={handleFileSelect}
                  featureLabel="Incident Correlation"
                />
                {selection && (
                  <p className="text-muted mt-2 text-xs">
                    Tracing <span className="text-ink font-mono">{selection.path}</span>
                  </p>
                )}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={handleCorrelate}
            disabled={status === "loading" || !canSubmit}
            className="bg-brand text-paper-white hover:bg-ink hover:text-paper self-end px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "Correlating…" : "Correlate →"}
          </button>
        </div>
      ) : (
        <div className="mt-8 flex items-baseline justify-between gap-4">
          <Metadata
            items={[
              incidentAtLocal ? new Date(incidentAtLocal).toLocaleString() : null,
              `${windowBeforeHours}h before`,
              useLlm ? "AI narrative" : "Raw",
            ]}
          />
          <button
            type="button"
            onClick={() => setConfigOpen(true)}
            className="text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors"
          >
            Re-run →
          </button>
        </div>
      )}

      {status === "error" && (
        <p className="text-muted mt-8 text-sm">
          Something went wrong correlating that window — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-16">
          {useLlm &&
            (result.used_llm && result.narrative ? (
              <RedPanel className="p-6 sm:p-8">
                <p className="text-sm leading-relaxed whitespace-pre-wrap sm:text-base">
                  {result.narrative}
                </p>
              </RedPanel>
            ) : result.llm_unavailable_reason ? (
              <div className="border-brand border p-6 sm:p-8">
                <SectionLabel tone="brand">AI narrative unavailable</SectionLabel>
                <p className="text-muted mt-3 text-sm leading-relaxed">
                  {UNAVAILABLE_MESSAGES[result.llm_unavailable_reason]}
                </p>
              </div>
            ) : null)}

          {result.file_trace.length > 0 && (
            <div className="mt-16">
              <div className="flex items-baseline gap-4">
                <SectionLabel tone="ink" className="text-base tracking-[0.15em]">
                  File Timeline
                </SectionLabel>
                <Rule className="flex-1" />
              </div>
              <ul className="mt-6 flex flex-col gap-8">
                {result.file_trace.map((commit) => (
                  <FileTraceCommit key={commit.sha} commit={commit} />
                ))}
              </ul>
            </div>
          )}

          <div className="mt-16">
            {result.sources.length === 0 ? (
              <p className="text-muted text-sm">
                Nothing ingested in that window — connect GitHub, Slack, or
                Jira, or widen it.
              </p>
            ) : (
              groupBySource(result.sources).map(([source, items]) => (
                <div key={source} className="mt-16 first:mt-0">
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
                            <span className="text-base font-medium text-ink">{item.title}</span>
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
                            new Date(item.occurred_at).toLocaleString(),
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
        </div>
      )}
    </div>
  );
}

/** A condensed version of Archaeology's own `CommitCard` — the incident
 * file trace is a secondary, supporting view alongside the time-window
 * results above, not the page's primary content, so it skips the
 * related-Slack/similar-issues/review-comment detail Archaeology's own
 * page renders in full. */
function FileTraceCommit({ commit }: { commit: CommitEntry }) {
  return (
    <li>
      <div className="flex items-baseline justify-between gap-4">
        <a
          href={commit.url}
          target="_blank"
          rel="noreferrer"
          className="hover:text-brand text-base font-medium text-ink transition-colors"
        >
          {commit.short_sha} — {commit.message.split("\n")[0]}
        </a>
        <AnnotateLink source="github" url={commit.url} title={commit.message.split("\n")[0]} />
      </div>
      <Metadata
        items={[
          commit.author,
          new Date(commit.committed_at).toLocaleString(),
          commit.pull_request ? `PR #${commit.pull_request.number}` : null,
          commit.jira_ticket_key,
        ]}
        className="mt-1"
      />
    </li>
  );
}

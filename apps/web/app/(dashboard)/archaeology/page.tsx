"use client";

import { useState } from "react";

import { RepoFilePicker, type RepoFileSelection } from "@/components/RepoFilePicker";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import { type ArchaeologyResponse, type CommitEntry, traceArchaeology } from "@/lib/archaeology";

export default function ArchaeologyPage() {
  const [selection, setSelection] = useState<RepoFileSelection | null>(null);
  const [result, setResult] = useState<ArchaeologyResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function handleSelect(next: RepoFileSelection) {
    setSelection(next);
    setStatus("loading");
    setResult(null);
    try {
      const response = await traceArchaeology(next);
      setResult(response);
      setStatus("idle");
    } catch (err) {
      setStatus("error");
      console.error(err instanceof ApiError ? err.message : err);
    }
  }

  return (
    <div>
      <SectionLabel tone="brand">Codebase Archaeology</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Why does this exist?
      </DisplayHeading>
      <p className="text-muted mt-4 max-w-md text-sm leading-relaxed">
        Pick a file. Relay traces its git blame back through each commit to the pull request that
        introduced it, the Jira ticket it closed, and any Slack discussion happening at the time.
      </p>

      <Rule className="mt-16" />

      <div className="mt-8 max-w-lg">
        <RepoFilePicker basePath="/v1/archaeology" onSelect={handleSelect} />
      </div>

      {status === "loading" && (
        <p className="text-muted mt-12 text-sm">Tracing {selection?.path}…</p>
      )}

      {status === "error" && (
        <p className="text-muted mt-12 text-sm">
          Something went wrong tracing that file — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-20">
          <SectionLabel>{selection?.path}</SectionLabel>

          {result.timeline.length === 0 ? (
            <p className="text-muted mt-6 text-sm">No blame history for this file.</p>
          ) : (
            <ul className="mt-6 flex flex-col gap-16">
              {result.timeline.map((commit) => (
                <CommitCard key={commit.sha} commit={commit} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function CommitCard({ commit }: { commit: CommitEntry }) {
  return (
    <li>
      <div className="flex items-baseline gap-4">
        <SectionLabel tone="ink" className="text-base tracking-[0.15em]">
          {commit.short_sha}
        </SectionLabel>
        <Rule className="flex-1" />
      </div>

      <a
        href={commit.url}
        target="_blank"
        rel="noreferrer"
        className="font-serif hover:text-brand mt-4 block max-w-2xl text-xl text-ink transition-colors sm:text-2xl"
      >
        {commit.message.split("\n")[0]}
      </a>
      <Metadata
        items={[
          commit.author,
          new Date(commit.committed_at).toLocaleDateString(),
          commit.line_ranges.length === 1
            ? `Lines ${commit.line_ranges[0].start}–${commit.line_ranges[0].end}`
            : `${commit.line_ranges.length} line ranges`,
        ]}
        className="mt-2"
      />

      {(commit.pull_request || commit.jira_ticket_key) && (
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
          {commit.pull_request && (
            <a
              href={commit.pull_request.url}
              target="_blank"
              rel="noreferrer"
              className="hover:text-brand text-sm font-medium text-ink transition-colors"
            >
              PR #{commit.pull_request.number} — {commit.pull_request.title}
            </a>
          )}
          {commit.jira_ticket_key &&
            (commit.jira_ticket_url ? (
              <a
                href={commit.jira_ticket_url}
                target="_blank"
                rel="noreferrer"
                className="text-brand text-xs font-medium tracking-[0.15em] uppercase transition-colors hover:underline"
              >
                {commit.jira_ticket_key}
              </a>
            ) : (
              <span className="text-brand text-xs font-medium tracking-[0.15em] uppercase">
                {commit.jira_ticket_key}
              </span>
            ))}
        </div>
      )}

      {commit.related_slack.length > 0 && (
        <ul className="border-line mt-6 flex flex-col gap-3 border-l pl-4">
          {commit.related_slack.map((msg) => (
            <li key={msg.url}>
              <a
                href={msg.url}
                target="_blank"
                rel="noreferrer"
                className="hover:text-brand text-sm font-medium text-ink transition-colors"
              >
                {msg.title}
              </a>
              <p className="text-muted mt-1 text-xs leading-relaxed">{msg.excerpt}</p>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

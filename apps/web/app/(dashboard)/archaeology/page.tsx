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
      const response = await traceArchaeology({
        owner: next.owner,
        repo: next.repo,
        ref: next.ref,
        path: next.path,
        target_type: next.targetType,
      });
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
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Pick a file. Relay traces its git blame back through each commit to the pull request that
        introduced it, the Jira ticket it closed, and any Slack discussion happening at the time.
      </p>

      <Rule className="mt-16" />

      <div className="mt-8 w-full lg:w-[60%]">
        <RepoFilePicker basePath="/v1/archaeology" onSelect={handleSelect} featureLabel="Archaeology" />
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
          <SectionLabel>{selection?.path || "Whole repository"}</SectionLabel>
          {result.files_total > 1 && (
            <p className="text-muted mt-2 text-xs">
              Analyzed {result.files_analyzed} of {result.files_total} files
              {result.files_skipped > 0 &&
                ` — ${result.files_skipped} skipped (binary or too large to blame)`}
            </p>
          )}

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
            : commit.line_ranges.length > 1
              ? `${commit.line_ranges.length} line ranges`
              : commit.files_touched.length > 1
                ? `${commit.files_touched.length} files`
                : null,
        ]}
        className="mt-2"
      />

      {commit.files_touched.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {commit.files_touched.map((f) => (
            <span
              key={f}
              className="border-line text-muted border px-2 py-0.5 font-mono text-[11px]"
            >
              {f}
            </span>
          ))}
        </div>
      )}

      {(commit.pull_request || commit.jira_ticket_key) && (
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
          {commit.pull_request && (
            <span className="flex items-center gap-2">
              <a
                href={commit.pull_request.url}
                target="_blank"
                rel="noreferrer"
                className="hover:text-brand text-sm font-medium text-ink transition-colors"
              >
                PR #{commit.pull_request.number} — {commit.pull_request.title}
              </a>
              {commit.pull_request.has_unresolved_review && (
                <span className="border-brand text-brand border px-1.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase">
                  Unresolved
                </span>
              )}
            </span>
          )}
          {commit.jira_ticket_key && (
            <p className="text-xs font-medium tracking-[0.15em] uppercase">
              <span className="text-muted">Jira · </span>
              {commit.jira_ticket_url ? (
                <a
                  href={commit.jira_ticket_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand transition-colors hover:underline"
                >
                  {commit.jira_ticket_key}
                </a>
              ) : (
                <span className="text-brand">{commit.jira_ticket_key}</span>
              )}
            </p>
          )}
        </div>
      )}

      {commit.related_slack.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Related Slack discussion
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
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
        </>
      )}

      {commit.similar_issues.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Similar past issues
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
            {commit.similar_issues.map((issue) => (
              <li key={issue.url}>
                <a
                  href={issue.url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-brand text-sm font-medium text-ink transition-colors"
                >
                  {issue.title}
                </a>
                <p className="text-muted mt-1 text-xs leading-relaxed">{issue.excerpt}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {commit.review_comments.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Code review
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
            {commit.review_comments.map((comment) => (
              <li key={comment.url}>
                <a
                  href={comment.url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-brand text-sm font-medium text-ink transition-colors"
                >
                  {comment.author ?? "Unknown reviewer"}
                  {comment.state ? ` · ${comment.state.replace("_", " ").toLowerCase()}` : ""}
                </a>
                <p className="text-muted mt-1 text-xs leading-relaxed">{comment.excerpt}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </li>
  );
}

"use client";

import { useState } from "react";

import { RepoFilePicker, type RepoFileSelection } from "@/components/RepoFilePicker";
import { AnnotateLink } from "@/components/editorial/AnnotateLink";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import {
  type PersonScore,
  type RankingStrategy,
  type WhoToAskResponse,
  rankWhoToAsk,
} from "@/lib/whoToAsk";

const COMMITS_SHOWN_COLLAPSED = 5;

export default function WhoToAskPage() {
  const [selection, setSelection] = useState<RepoFileSelection | null>(null);
  const [strategy, setStrategy] = useState<RankingStrategy>("recency");
  const [result, setResult] = useState<WhoToAskResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  async function runRank(next: RepoFileSelection, nextStrategy: RankingStrategy) {
    setStatus("loading");
    setResult(null);
    try {
      const response = await rankWhoToAsk({
        owner: next.owner,
        repo: next.repo,
        ref: next.ref,
        path: next.path,
        target_type: next.targetType,
        pr_number: next.prNumber,
        strategy: nextStrategy,
      });
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
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Pick a file, a directory, or a pull request. Relay ranks everyone who&apos;s touched it —
        by how recently, or how often — using its git blame history.
      </p>

      <Rule className="mt-16" />

      {/* Same label + toggle shape as Search/Weekly Digest's own selectors. */}
      <div className="mt-8 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
        <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
          Sort
        </SectionLabel>
        <div className="border-line flex w-full border sm:w-[420px]">
          {(["recency", "frequency"] as const).map((s, i) => (
            <button
              key={s}
              type="button"
              aria-pressed={strategy === s}
              onClick={() => handleStrategyChange(s)}
              className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                i === 1 ? "border-line border-l" : ""
              } ${strategy === s ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
            >
              {s === "recency" ? "Recently active" : "Most involved"}
            </button>
          ))}
        </div>
      </div>

      <Rule className="mt-8 w-full lg:w-[60%]" />

      <div className="mt-8 w-full lg:w-[60%]">
        <RepoFilePicker basePath="/v1/who-to-ask" onSelect={handleSelect} />
      </div>

      {status === "loading" && (
        <p className="text-muted mt-12 text-sm">
          Ranking {selection?.displayLabel || selection?.path}…
        </p>
      )}

      {status === "error" && (
        <p className="text-muted mt-12 text-sm">
          Something went wrong ranking that file — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-20">
          <SectionLabel>
            {selection?.displayLabel || selection?.path || "Whole repository"}
          </SectionLabel>
          {result.files_total > 1 && (
            <p className="text-muted mt-2 text-xs">
              Analyzed {result.files_analyzed} of {result.files_total} files
              {result.files_skipped > 0 &&
                ` — ${result.files_skipped} skipped (binary or too large to blame)`}
            </p>
          )}

          {result.people.length === 0 ? (
            <p className="text-muted mt-6 text-sm">No blame history for this file.</p>
          ) : (
            <ul className="mt-6 flex flex-col gap-10">
              {result.people.map((person, i) => (
                <PersonCard key={person.author} person={person} rank={i + 1} topScore={topScore} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function PersonCard({
  person,
  rank,
  topScore,
}: {
  person: PersonScore;
  rank: number;
  topScore: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = person.commits.length > COMMITS_SHOWN_COLLAPSED;
  const visibleCommits = expanded ? person.commits : person.commits.slice(0, COMMITS_SHOWN_COLLAPSED);

  return (
    <li>
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-serif text-xl text-ink sm:text-2xl">{person.author}</p>
        <span className="text-muted text-xs tracking-[0.1em] uppercase">#{rank}</span>
      </div>
      <div className="border-line mt-3 h-1.5 w-full border">
        <div
          className="bg-brand h-full"
          style={{ width: `${Math.max((person.score / topScore) * 100, 4)}%` }}
        />
      </div>
      <Metadata
        items={[
          person.commits.length > 0
            ? `${person.commits.length} commit${person.commits.length === 1 ? "" : "s"}`
            : null,
          person.reviews.length > 0
            ? `${person.reviews.length} review${person.reviews.length === 1 ? "" : "s"}`
            : null,
          `Last active ${new Date(person.last_touch_at).toLocaleDateString()}`,
        ]}
        className="mt-3"
      />

      {person.jira_ticket_key && (
        <span className="mt-3 flex items-center gap-3">
          <p className="text-xs font-medium tracking-[0.15em] uppercase">
            <span className="text-muted">Jira · </span>
            {person.jira_ticket_url ? (
              <a
                href={person.jira_ticket_url}
                target="_blank"
                rel="noreferrer"
                className="text-brand transition-colors hover:underline"
              >
                {person.jira_ticket_key}
              </a>
            ) : (
              <span className="text-brand">{person.jira_ticket_key}</span>
            )}
          </p>
          {person.jira_ticket_url && (
            <AnnotateLink
              source="jira"
              url={person.jira_ticket_url}
              title={person.jira_ticket_key}
            />
          )}
        </span>
      )}

      {person.related_slack.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-4">
            Related Slack discussion
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
            {person.related_slack.map((msg) => (
              <li key={msg.url}>
                <div className="flex items-baseline justify-between gap-4">
                  <a
                    href={msg.url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-brand text-sm font-medium text-ink transition-colors"
                  >
                    {msg.title}
                  </a>
                  <AnnotateLink source="slack" url={msg.url} title={msg.title} />
                </div>
                <p className="text-muted mt-1 text-xs leading-relaxed">{msg.excerpt}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {person.similar_issues.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-4">
            Similar past issues
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
            {person.similar_issues.map((issue) => (
              <li key={issue.url}>
                <div className="flex items-baseline justify-between gap-4">
                  <a
                    href={issue.url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-brand text-sm font-medium text-ink transition-colors"
                  >
                    {issue.title}
                  </a>
                  <AnnotateLink source="jira" url={issue.url} title={issue.title} />
                </div>
                <p className="text-muted mt-1 text-xs leading-relaxed">{issue.excerpt}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {person.commits.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-4">
            Commits
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-2 border-l pl-4">
            {visibleCommits.map((commit) => (
              <li key={commit.sha}>
                <div className="flex items-baseline justify-between gap-4">
                  <a
                    href={commit.url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-brand text-sm text-ink transition-colors"
                  >
                    {commit.message}
                  </a>
                  <AnnotateLink source="github" url={commit.url} title={commit.message} />
                </div>
                <Metadata
                  items={[commit.short_sha, new Date(commit.committed_at).toLocaleDateString()]}
                  className="mt-0.5"
                />
              </li>
            ))}
          </ul>
          {hasMore && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="text-brand hover:text-ink mt-3 text-xs font-medium tracking-[0.1em] uppercase transition-colors"
            >
              {expanded ? "Show fewer" : `Show all ${person.commits.length} commits`}
            </button>
          )}
        </>
      )}

      {person.reviews.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-4">
            Reviews
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-2 border-l pl-4">
            {person.reviews.map((review, i) => (
              <li key={`${review.url}-${i}`}>
                <div className="flex items-baseline justify-between gap-4">
                  <a
                    href={review.url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-brand text-sm text-ink transition-colors"
                  >
                    PR #{review.pr_number} — {review.pr_title}
                  </a>
                  <AnnotateLink
                    source="github"
                    url={review.url}
                    title={`PR #${review.pr_number} — ${review.pr_title}`}
                  />
                </div>
                <Metadata
                  items={[
                    review.state?.replace("_", " ").toLowerCase() ?? null,
                    new Date(review.occurred_at).toLocaleDateString(),
                  ]}
                  className="mt-0.5"
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </li>
  );
}

"use client";

import { useEffect, useState } from "react";

import { AnnotateLink } from "@/components/editorial/AnnotateLink";
import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import { type DecisionDebtResponse, type RelatedItem, scanDecisionDebt } from "@/lib/decisionDebt";
import { type RepoOption, fetchRepos } from "@/lib/repoBrowser";

const DISCUSSION_THRESHOLDS = [
  { value: 2, label: "2+" },
  { value: 3, label: "3+" },
  { value: 5, label: "5+" },
] as const;

const INACTIVE_WINDOWS = [
  { value: 90, label: "90d" },
  { value: 180, label: "180d" },
  { value: 365, label: "365d" },
] as const;

const SOURCE_LABELS: Record<RelatedItem["source"], string> = {
  slack: "Slack",
  jira: "Jira",
  github: "GitHub",
};

export default function DecisionDebtPage() {
  const [repos, setRepos] = useState<RepoOption[] | null>(null);
  const [repoStatus, setRepoStatus] = useState<"idle" | "loading" | "error">("loading");
  const [selectedRepo, setSelectedRepo] = useState<RepoOption | null>(null);

  const [minDiscussionItems, setMinDiscussionItems] = useState(2);
  const [inactiveAfterDays, setInactiveAfterDays] = useState(180);

  const [result, setResult] = useState<DecisionDebtResponse | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    fetchRepos("/v1/archaeology")
      .then((r) => {
        setRepos(r);
        setRepoStatus("idle");
      })
      .catch((err: unknown) => {
        setRepoStatus("error");
        console.error(err instanceof ApiError ? err.message : err);
      });
  }, []);

  async function handleScan() {
    if (!selectedRepo) return;
    setStatus("loading");
    try {
      const response = await scanDecisionDebt({
        owner: selectedRepo.owner,
        repo: selectedRepo.name,
        minDiscussionItems,
        inactiveAfterDays,
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
      <SectionLabel tone="brand">Decision Debt</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        What never got written down?
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Pull requests with real Slack or Jira discussion behind them, but
        no correlated decision doc — a change that clearly involved
        deliberation, with nothing recording why it went the way it did.
      </p>

      <Rule className="mt-16" />

      <div className="mt-8 flex flex-col gap-6 sm:max-w-[496px]">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-3">
          <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0 sm:pt-2">
            Repo
          </SectionLabel>
          <div className="border-line w-full border sm:w-[420px]">
            {repoStatus === "loading" && (
              <p className="text-muted px-4 py-3 text-sm">Loading repositories…</p>
            )}
            {repoStatus === "error" && (
              <p className="text-muted px-4 py-3 text-sm">
                Couldn&rsquo;t load repos — connect GitHub on the Connections page.
              </p>
            )}
            {repos && repos.length === 0 && (
              <p className="text-muted px-4 py-3 text-sm">No repositories found.</p>
            )}
            {repos?.map((repo, i) => (
              <button
                key={repo.full_name}
                type="button"
                onClick={() => setSelectedRepo(repo)}
                className={`block w-full px-4 py-2.5 text-left text-sm transition-colors ${
                  i > 0 ? "border-line border-t" : ""
                } ${
                  selectedRepo?.full_name === repo.full_name
                    ? "bg-ink text-paper"
                    : "text-ink hover:bg-line/30"
                }`}
              >
                {repo.full_name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
            Discuss.
          </SectionLabel>
          <div className="border-line flex w-full border sm:w-[420px]">
            {DISCUSSION_THRESHOLDS.map((t, i) => (
              <button
                key={t.value}
                type="button"
                aria-pressed={minDiscussionItems === t.value}
                onClick={() => setMinDiscussionItems(t.value)}
                className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                  i > 0 ? "border-line border-l" : ""
                } ${
                  minDiscussionItems === t.value
                    ? "bg-ink text-paper"
                    : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <SectionLabel tone="brand" className="sm:w-16 sm:shrink-0">
            Inactive
          </SectionLabel>
          <div className="border-line flex w-full border sm:w-[420px]">
            {INACTIVE_WINDOWS.map((w, i) => (
              <button
                key={w.value}
                type="button"
                aria-pressed={inactiveAfterDays === w.value}
                onClick={() => setInactiveAfterDays(w.value)}
                className={`flex-1 px-4 py-2 text-center text-xs font-medium tracking-[0.15em] uppercase transition-colors ${
                  i > 0 ? "border-line border-l" : ""
                } ${
                  inactiveAfterDays === w.value
                    ? "bg-ink text-paper"
                    : "text-muted hover:text-ink"
                }`}
              >
                {w.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={handleScan}
          disabled={status === "loading" || !selectedRepo}
          className="bg-brand text-paper-white hover:bg-ink hover:text-paper self-end px-4 py-2 text-xs font-medium tracking-[0.15em] uppercase transition-colors disabled:opacity-50"
        >
          {status === "loading" ? "Scanning…" : "Scan →"}
        </button>
      </div>

      {status === "error" && (
        <p className="text-muted mt-8 text-sm">
          Something went wrong scanning that repo — try again in a moment.
        </p>
      )}

      {result && (
        <div className="mt-16">
          <Metadata
            items={[
              `${result.prs_scanned} PRs scanned`,
              `${result.decision_docs_found} decision docs found`,
              `${result.flagged.length} flagged`,
            ]}
          />

          {result.flagged.length === 0 ? (
            <p className="text-muted mt-6 text-sm">
              Nothing flagged — every well-discussed change in this repo has a
              correlated decision doc, or nothing cleared the discussion threshold.
            </p>
          ) : (
            <ul className="mt-10 flex flex-col gap-16">
              {result.flagged.map((pr) => (
                <FlaggedPullRequestCard key={pr.number} pr={pr} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function FlaggedPullRequestCard({ pr }: { pr: DecisionDebtResponse["flagged"][number] }) {
  return (
    <li>
      <div className="flex items-baseline gap-4">
        <SectionLabel tone="ink" className="text-base tracking-[0.15em]">
          PR #{pr.number}
        </SectionLabel>
        <Rule className="flex-1" />
      </div>

      <div className="mt-4 flex items-baseline justify-between gap-4">
        <a
          href={pr.url}
          target="_blank"
          rel="noreferrer"
          className="font-serif hover:text-brand block max-w-2xl text-xl text-ink transition-colors sm:text-2xl"
        >
          {pr.title}
        </a>
        <AnnotateLink source="github" url={pr.url} title={pr.title} />
      </div>

      <div className="mt-2 flex items-center gap-3">
        <Metadata items={[pr.author]} />
        {pr.author_inactive && (
          <span className="border-brand text-brand border px-1.5 py-0.5 text-[10px] font-medium tracking-[0.1em] uppercase">
            Author inactive
          </span>
        )}
      </div>

      {pr.discussion.length > 0 && (
        <div className="mt-5 flex flex-col gap-3">
          {pr.discussion.map((item) => (
            <div key={item.url}>
              <div className="flex items-baseline justify-between gap-4">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-brand text-sm font-medium text-ink transition-colors"
                >
                  {item.title}
                </a>
                <span className="text-muted shrink-0 text-xs uppercase tracking-[0.1em]">
                  {SOURCE_LABELS[item.source]}
                </span>
              </div>
              <p className="text-muted mt-1 text-sm leading-relaxed">{item.excerpt}</p>
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

"use client";

import { useEffect, useState } from "react";

import { DisplayHeading } from "@/components/editorial/DisplayHeading";
import { Metadata } from "@/components/editorial/Metadata";
import { Rule } from "@/components/editorial/Rule";
import { SectionLabel } from "@/components/editorial/SectionLabel";
import { ApiError } from "@/lib/api";
import { type WorkflowVerdict, fetchWorkflows } from "@/lib/flakyTests";
import { type RepoOption, fetchRepos } from "@/lib/repoBrowser";

const VERDICT_LABELS: Record<WorkflowVerdict["verdict"], string> = {
  broken: "Broken",
  flaky: "Flaky",
  stable: "Stable",
  unknown: "Unknown",
};

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 400) return "Connect GitHub on the Connections page first.";
    if (err.status === 401) return "Your session expired — sign in again.";
    return `Request failed (${err.status}).`;
  }
  return "Couldn't reach the server — check that the backend is running.";
}

export default function FlakyTestsPage() {
  const [repos, setRepos] = useState<RepoOption[] | "loading">("loading");
  const [reposError, setReposError] = useState<string | null>(null);
  const [repo, setRepo] = useState<RepoOption | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowVerdict[] | "loading" | null>(null);
  const [workflowsError, setWorkflowsError] = useState<string | null>(null);

  useEffect(() => {
    fetchRepos("/v1/flaky-tests")
      .then((r) => {
        setRepos(r);
        setReposError(null);
      })
      .catch((err: unknown) => {
        console.error(err);
        setReposError(describeError(err));
      });
  }, []);

  async function selectRepo(next: RepoOption) {
    setRepo(next);
    setWorkflows("loading");
    setWorkflowsError(null);
    try {
      setWorkflows(await fetchWorkflows(next.owner, next.name));
    } catch (err) {
      console.error(err);
      setWorkflowsError(describeError(err));
      setWorkflows(null);
    }
  }

  function changeRepo() {
    setRepo(null);
    setWorkflows(null);
    setWorkflowsError(null);
  }

  return (
    <div>
      <SectionLabel tone="brand">Flaky Test Investigator</SectionLabel>
      <DisplayHeading size="xl" className="text-ink mt-3">
        Is this really broken?
      </DisplayHeading>
      <p className="text-muted mt-6 max-w-md text-sm leading-relaxed">
        Pick a repo. Relay tracks each workflow&apos;s recent pass/fail history and flags the ones
        that look flaky rather than genuinely broken — a same-commit re-run succeeding is the
        clearest sign.
      </p>

      <Rule className="mt-16" />

      {!repo ? (
        <div className="mt-8 w-full lg:w-[60%]">
          <SectionLabel tone="brand">Repository</SectionLabel>
          <Rule className="mt-3" />
          {reposError ? (
            <p className="text-brand mt-6 text-sm">{reposError}</p>
          ) : repos === "loading" ? (
            <p className="text-muted mt-6 text-sm">Loading repositories…</p>
          ) : repos.length === 0 ? (
            <p className="text-muted mt-6 text-sm">
              No repositories found — connect GitHub first.
            </p>
          ) : (
            <ul>
              {repos.map((r) => (
                <li key={r.full_name} className="border-line border-b">
                  <button
                    type="button"
                    onClick={() => selectRepo(r)}
                    className="hover:text-brand w-full py-3 text-left text-sm font-medium text-ink transition-colors"
                  >
                    {r.full_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="mt-8">
          <div className="flex items-baseline gap-4">
            <SectionLabel tone="brand" className="truncate">
              {repo.full_name}
            </SectionLabel>
            <button
              type="button"
              onClick={changeRepo}
              className="text-muted hover:text-ink shrink-0 text-xs font-medium tracking-[0.15em] uppercase transition-colors"
            >
              Change repo
            </button>
          </div>

          {workflowsError ? (
            <p className="text-brand mt-8 text-sm">{workflowsError}</p>
          ) : workflows === "loading" ? (
            <p className="text-muted mt-8 text-sm">Analyzing workflows…</p>
          ) : workflows && workflows.length === 0 ? (
            <p className="text-muted mt-8 text-sm">
              No CI activity found for this repo yet — Relay syncs recent GitHub Actions history
              every 15 minutes.
            </p>
          ) : workflows ? (
            <ul className="mt-8 flex flex-col gap-16">
              {workflows.map((w) => (
                <WorkflowCard key={`${w.workflow_name}::${w.head_branch}`} workflow={w} />
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}

function WorkflowCard({ workflow }: { workflow: WorkflowVerdict }) {
  return (
    <li>
      <div className="flex items-baseline gap-4">
        <SectionLabel
          tone={workflow.verdict === "stable" ? "muted" : "brand"}
          className="text-base tracking-[0.15em]"
        >
          {VERDICT_LABELS[workflow.verdict]}
        </SectionLabel>
        <Rule className="flex-1" />
      </div>

      <p className="font-serif mt-4 text-xl text-ink sm:text-2xl">
        {workflow.workflow_name}
        <span className="text-muted ml-2 text-base">· {workflow.head_branch}</span>
      </p>

      <Metadata
        items={[
          workflow.total_considered > 0
            ? `${workflow.passed_count} of ${workflow.total_considered} runs passed`
            : "No completed runs yet",
          workflow.rerun_count > 0
            ? `${workflow.rerun_count} same-commit re-run${workflow.rerun_count === 1 ? "" : "s"} detected`
            : null,
        ]}
        className="mt-2"
      />

      {workflow.verdict === "flaky" &&
        workflow.flaky_test_cases.length === 0 &&
        workflow.has_test_case_data && (
          <p className="text-muted mt-3 max-w-md text-xs leading-relaxed">
            No individual test was confirmed as the flaky one — captured test-case data
            didn&apos;t show any single test flipping pass/fail, so this may be an
            infrastructure or setup issue rather than a specific test.
          </p>
        )}

      {workflow.recent_runs.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Recent runs
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-2 border-l pl-4">
            {workflow.recent_runs.map((run) => (
              <li key={run.run_id}>
                <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <a
                    href={run.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-brand text-sm text-ink transition-colors"
                  >
                    {run.conclusion ?? run.status}
                  </a>
                  {run.pull_requests.map((pr) => (
                    <a
                      key={pr.number}
                      href={pr.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-brand text-xs font-medium text-ink transition-colors"
                    >
                      PR #{pr.number}
                    </a>
                  ))}
                </div>
                <Metadata
                  items={[
                    run.head_sha.slice(0, 7),
                    new Date(run.run_started_at).toLocaleDateString(),
                    run.run_attempt > 1 ? `attempt ${run.run_attempt}` : null,
                  ]}
                  className="mt-0.5"
                />
              </li>
            ))}
          </ul>
        </>
      )}

      {workflow.flaky_test_cases.length > 0 && (
        <>
          <SectionLabel tone="muted" className="mt-6">
            Flaky tests
          </SectionLabel>
          <ul className="border-line mt-2 flex flex-col gap-3 border-l pl-4">
            {workflow.flaky_test_cases.map((tc) => (
              <li key={`${tc.classname}::${tc.test_name}`}>
                <p className="text-sm font-medium text-ink">
                  {tc.classname ? `${tc.classname}.` : ""}
                  {tc.test_name}
                </p>
                <Metadata
                  items={[
                    tc.verdict === "broken" ? "Broken" : "Flaky",
                    `${tc.passed_count} of ${tc.total_considered} runs passed`,
                  ]}
                  className="mt-1"
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </li>
  );
}

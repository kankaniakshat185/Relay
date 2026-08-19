import { apiFetch } from "./api";

export type Verdict = "stable" | "flaky" | "broken" | "unknown";

export interface PullRequestRef {
  number: number;
  url: string;
}

export interface RunSummary {
  run_id: number;
  conclusion: string | null;
  status: string;
  run_attempt: number;
  head_sha: string;
  html_url: string;
  run_started_at: string;
  pull_requests: PullRequestRef[];
}

export interface TestCaseVerdict {
  classname: string;
  test_name: string;
  verdict: Verdict;
  total_considered: number;
  passed_count: number;
  failed_count: number;
}

export interface WorkflowVerdict {
  workflow_name: string;
  head_branch: string;
  verdict: Verdict;
  total_considered: number;
  passed_count: number;
  failed_count: number;
  rerun_count: number;
  recent_runs: RunSummary[];
  /** Best-effort — empty whenever no JUnit-shaped test-report artifact
   * was captured for this workflow's runs. */
  flaky_test_cases: TestCaseVerdict[];
  /** False means no test-case data was ever captured — can't confirm
   * either way. True with an empty `flaky_test_cases` means data exists
   * and genuinely no individual test looks flaky. */
  has_test_case_data: boolean;
}

export async function fetchWorkflows(owner: string, repo: string): Promise<WorkflowVerdict[]> {
  const params = new URLSearchParams({ owner, repo });
  return apiFetch<WorkflowVerdict[]>(`/v1/flaky-tests/workflows?${params.toString()}`);
}

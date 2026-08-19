# ADR 0019: Flaky Test Investigator — best-effort individual test-case detail

**Status:** Accepted — Phase 3, Build 2 of 2 (workflow-run level is Build
1, ADR 0018)

## What

Layers individual-test-case flakiness on top of Build 1's workflow-run
verdicts, without replacing them:

- `connectors/github/client.py`: `list_run_artifacts`, `download_artifact`.
- `features/flaky_tests/junit_parser.py`: stdlib-only (`zipfile` +
  `xml.etree.ElementTree`) JUnit-XML parsing, returns `[]` — never
  raises — for anything unparseable.
- `features/flaky_tests/models.py`: `CaseResult`, a new table
  (`flaky_test_case_results`), FK to `WorkflowRun`.
- `jobs/flaky_tests.py`: for the most recent completed runs *per
  workflow* that don't have test-case data yet, fetches artifacts and
  attempts to parse one as a JUnit report.
- `WorkflowVerdict.flaky_test_cases`: individual tests whose own history
  looks flaky or broken, empty whenever no test-case data was captured.

## Why "best-effort," stated as a first-class design constraint, not a caveat

Not every repo's CI produces a JUnit-shaped artifact — many don't produce
any test-report artifact at all, and this is normal, not a gap. Every
decision here follows from that:

- **JUnit XML specifically**, not because every repo uses it, but because
  it's the closest thing to a de facto standard multiple ecosystems can
  produce (pytest's `--junitxml`, Jest via a reporter, JUnit/Maven/Gradle
  natively) — supporting it covers the most ground for the least parser
  complexity, without trying to special-case every framework's native
  format.
- **The parser never raises.** Malformed XML, a non-JUnit root element, a
  zip with no XML at all, a zip that isn't actually a zip — all return
  `[]`. A caller scanning several files in an artifact, or several
  artifacts on a run, treats every outcome identically: try the next one,
  or accept that this run has no captured test-case data.
- **A workflow's own verdict never depends on this data existing.**
  Build 1's `_compute_verdict` is untouched; `flaky_test_cases` is a pure
  addition alongside it.

**Live-verified, and this is why the "never raises" design mattered in
practice**: a real sync against a connected account hit **20+ real
non-JUnit artifacts** (`coverage-html.zip`, from a coverage tool, across
several repos) — every single one downloaded successfully (including
following GitHub's redirect to Azure blob storage) and was correctly
recognized as "not a test report," with zero errors and zero incorrectly
ingested rows. This wasn't a hypothetical edge case worth testing in the
abstract — it was the *actual, common* case the very first live run hit.

## The `_ARTIFACT_FETCH_LIMIT` cap is per workflow, not per repo

Unlike `_RUN_FETCH_LIMIT` (Build 1, per repo), artifact fetching is
capped **per workflow** deliberately: downloading and parsing an artifact
is a real file transfer + unzip + XML parse, meaningfully heavier than
listing run metadata, and a per-repo cap would let one frequently-run
workflow consume the whole budget, starving every other workflow in the
same repo of any test-case data at all.

## Completed runs are immutable — artifact fetching runs at most once per run

A run's test results, once the run is `completed`, never change (unlike
its `conclusion`/`status`, which can transition — see ADR 0018's
in-progress→completed test). `jobs/flaky_tests.py` checks whether a run
already has `CaseResult` rows before attempting artifact fetch, so a
resync never re-downloads or re-parses an artifact it's already
processed — verified directly: a dedicated test proves the second sync
in a row makes zero `list_run_artifacts` calls for an already-processed
run.

## Per-test verdicts have no rerun signal, unlike per-workflow ones

`_compute_test_case_verdict` is deliberately simpler than
`_compute_verdict` (ADR 0018) — it has no equivalent to the "same-commit
re-run" signal, because a re-run is tracked per *workflow run*, not per
individual test within it. Every test in a rerun run would show the
identical "same commit, different result" signal, so it wouldn't
discriminate between which specific tests are actually flaky — the
rerun-as-flaky-override only makes sense at the granularity it was
designed for.

## A workflow-level verdict and its own flaky test cases are not required to agree

`WorkflowVerdict.verdict` (Build 1) and `WorkflowVerdict.flaky_test_cases`
(Build 2) answer different questions and are computed independently — a
workflow that reads `stable` overall could, in principle, still have an
individual test whose outcome varied if the CI configuration doesn't
propagate every test failure to the run's own conclusion. Neither is
"more correct"; both are shown.

## What this does NOT do

No historical trend beyond what's still in the ingestion window (`_RUN_FETCH_LIMIT`,
Build 1) — a test's flakiness is judged only from currently-ingested
runs, not the repo's entire history. No cross-run test identity beyond
`(classname, test_name)` matching exactly — a renamed test starts a fresh
history under its new name, same limitation as any name-based tracking.
No support for test frameworks that don't produce JUnit-shaped XML at
all; that's a real ceiling on today's scope, not a bug.

"""Best-effort JUnit-XML parsing for individual test-case outcomes — the
Build 2 layer of Flaky Test Investigator (ADR 0019). JUnit XML is the
target format because it's the de facto standard most languages' test
runners can produce (pytest's `--junitxml`, Jest via a reporter, JUnit/
Maven/Gradle natively) — not because every repo produces it. Anything
that doesn't look like JUnit XML, or isn't present in an artifact at all,
returns an empty list here, never an error: "no parseable test report"
is an expected, common outcome for a workflow that doesn't upload one,
not a failure worth surfacing.

Stdlib only (`zipfile` + `xml.etree.ElementTree`) — no new dependency for
what's fundamentally "unzip a small text file and read some attributes."
"""

import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

_OUTCOME_TAGS = {"failure": "failed", "error": "failed", "skipped": "skipped"}
"""A `<testcase>` with none of these child elements passed — JUnit XML
signals failure/error/skip by the *presence* of a child tag, not an
attribute, so "no matching child" is the pass case, not a missing field."""


@dataclass(frozen=True)
class TestCaseOutcome:
    classname: str
    name: str
    outcome: str
    """`"passed" | "failed" | "skipped"`."""
    duration_seconds: float | None


def _local_tag(tag: str) -> str:
    """Strips an XML namespace prefix (`{http://...}testcase` → `testcase`)
    — some JUnit producers namespace their output, most don't; this
    handles both without needing to know which in advance."""
    return tag.rsplit("}", 1)[-1]


def _parse_testcase(elem: ElementTree.Element) -> TestCaseOutcome:
    outcome = "passed"
    for child in elem:
        tag = _local_tag(child.tag)
        if tag in _OUTCOME_TAGS:
            outcome = _OUTCOME_TAGS[tag]
            break

    time_attr = elem.get("time")
    try:
        duration = float(time_attr) if time_attr is not None else None
    except ValueError:
        duration = None

    return TestCaseOutcome(
        classname=elem.get("classname", ""),
        name=elem.get("name") or "(unnamed test)",
        outcome=outcome,
        duration_seconds=duration,
    )


def parse_junit_xml(xml_bytes: bytes) -> list[TestCaseOutcome]:
    """Returns `[]` for anything that isn't parseable JUnit-shaped XML —
    malformed XML, a root element that isn't `testsuite`/`testsuites`, or
    no `<testcase>` elements found inside. Never raises; a caller scanning
    several files in an artifact treats every result the same way."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    if _local_tag(root.tag) not in ("testsuite", "testsuites"):
        return []

    testcases = [elem for elem in root.iter() if _local_tag(elem.tag) == "testcase"]
    return [_parse_testcase(elem) for elem in testcases]


_MAX_FILES_SCANNED = 20
"""How many files inside one artifact zip to check before giving up —
bounds the work for an artifact that happens to contain many files none
of which are a test report (e.g. coverage HTML, build logs bundled
alongside)."""


def find_and_parse_junit_report(zip_bytes: bytes) -> list[TestCaseOutcome]:
    """Given a downloaded artifact zip, finds the first `.xml` file inside
    that actually parses as a JUnit-shaped report and returns its test
    cases. Returns `[]` if the zip itself can't be read, or nothing
    inside looks like a test report — both expected, common outcomes for
    an artifact that isn't a test-results bundle at all."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            for name in xml_names[:_MAX_FILES_SCANNED]:
                outcomes = parse_junit_xml(archive.read(name))
                if outcomes:
                    return outcomes
    except zipfile.BadZipFile:
        return []
    return []

"""`features/flaky_tests/junit_parser.py` — pure, no DB/network. Both
public functions are designed to return `[]` rather than raise on
anything unparseable; every "unhappy path" test here asserts exactly
that, not an exception."""

import zipfile
from io import BytesIO

from relay_api.features.flaky_tests import junit_parser

_VALID_JUNIT_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="3" failures="1" errors="0" skipped="1">
  <testcase classname="tests.test_math" name="test_add" time="0.001" />
  <testcase classname="tests.test_math" name="test_subtract" time="0.002">
    <failure message="assert 1 == 2">AssertionError</failure>
  </testcase>
  <testcase classname="tests.test_math" name="test_divide" time="0.000">
    <skipped />
  </testcase>
</testsuite>
"""

_NESTED_TESTSUITES_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="suite-a">
    <testcase classname="a" name="test_one" time="0.1" />
  </testsuite>
  <testsuite name="suite-b">
    <testcase classname="b" name="test_two" time="0.2">
      <error message="boom">Traceback...</error>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parses_a_flat_testsuite() -> None:
    outcomes = junit_parser.parse_junit_xml(_VALID_JUNIT_XML)

    assert len(outcomes) == 3
    by_name = {o.name: o for o in outcomes}
    assert by_name["test_add"].outcome == "passed"
    assert by_name["test_subtract"].outcome == "failed"
    assert by_name["test_divide"].outcome == "skipped"
    assert by_name["test_add"].classname == "tests.test_math"
    assert by_name["test_add"].duration_seconds == 0.001


def test_parses_nested_testsuites_across_multiple_suites() -> None:
    outcomes = junit_parser.parse_junit_xml(_NESTED_TESTSUITES_XML)

    assert len(outcomes) == 2
    by_name = {o.name: o for o in outcomes}
    assert by_name["test_one"].outcome == "passed"
    assert by_name["test_two"].outcome == "failed"  # <error> counts as failed, same as <failure>


def test_error_tag_and_failure_tag_both_count_as_failed() -> None:
    xml = b"""<testsuite>
      <testcase classname="x" name="a"><failure /></testcase>
      <testcase classname="x" name="b"><error /></testcase>
    </testsuite>"""

    outcomes = junit_parser.parse_junit_xml(xml)

    assert {o.outcome for o in outcomes} == {"failed"}


def test_malformed_xml_returns_empty_list_not_an_exception() -> None:
    assert junit_parser.parse_junit_xml(b"<not><valid</xml") == []


def test_non_junit_xml_root_returns_empty_list() -> None:
    assert junit_parser.parse_junit_xml(b"<html><body>not a test report</body></html>") == []


def test_missing_time_attribute_leaves_duration_none() -> None:
    xml = b'<testsuite><testcase classname="x" name="a" /></testsuite>'

    outcomes = junit_parser.parse_junit_xml(xml)

    assert outcomes[0].duration_seconds is None


def _zip_of(files: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buf.getvalue()


def test_finds_and_parses_a_junit_report_inside_a_zip() -> None:
    zip_bytes = _zip_of({"results.xml": _VALID_JUNIT_XML})

    outcomes = junit_parser.find_and_parse_junit_report(zip_bytes)

    assert len(outcomes) == 3


def test_skips_non_junit_xml_files_and_finds_the_real_report() -> None:
    zip_bytes = _zip_of(
        {
            "coverage.xml": b"<coverage><package /></coverage>",
            "results.xml": _VALID_JUNIT_XML,
        }
    )

    outcomes = junit_parser.find_and_parse_junit_report(zip_bytes)

    assert len(outcomes) == 3


def test_returns_empty_list_when_zip_has_no_xml_at_all() -> None:
    zip_bytes = _zip_of({"build.log": b"some log output, not xml"})

    assert junit_parser.find_and_parse_junit_report(zip_bytes) == []


def test_returns_empty_list_for_a_zip_with_no_parseable_report() -> None:
    zip_bytes = _zip_of({"coverage.xml": b"<coverage><package /></coverage>"})

    assert junit_parser.find_and_parse_junit_report(zip_bytes) == []


def test_not_a_zip_at_all_returns_empty_list_not_an_exception() -> None:
    assert junit_parser.find_and_parse_junit_report(b"this is not a zip file") == []

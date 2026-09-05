from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from relay_api.features.incident_correlation.schemas import IncidentCorrelationRequest


def test_file_path_without_owner_repo_ref_is_rejected() -> None:
    with pytest.raises(ValidationError, match="owner, repo, and ref"):
        IncidentCorrelationRequest(incident_at=datetime.now(UTC), file_path="src/x.py")


def test_file_path_with_owner_repo_ref_is_accepted() -> None:
    request = IncidentCorrelationRequest(
        incident_at=datetime.now(UTC),
        file_path="src/x.py",
        owner="acme",
        repo="widgets",
        ref="main",
    )
    assert request.file_path == "src/x.py"


def test_no_file_path_needs_no_repo_fields() -> None:
    request = IncidentCorrelationRequest(incident_at=datetime.now(UTC))
    assert request.file_path is None


def test_a_naive_incident_at_is_assumed_utc_not_rejected() -> None:
    # A browser's <input type="datetime-local"> has no timezone at all —
    # this must not raise, and must not silently misinterpret local time.
    naive = datetime(2026, 1, 15, 12, 0)
    request = IncidentCorrelationRequest(incident_at=naive)
    assert request.incident_at.tzinfo is not None
    assert request.incident_at == datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def test_a_timezone_aware_incident_at_is_left_unchanged() -> None:
    aware = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    request = IncidentCorrelationRequest(incident_at=aware)
    assert request.incident_at == aware

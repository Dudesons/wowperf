# ABOUTME: Behaviour tests for the finding type and its ranking.
# ABOUTME: The confidence badge is mandatory, so its absence must be an error.

import pytest
from pydantic import ValidationError

from wowperf.domain.findings import Confidence, Finding, rank_findings


def a_finding(finding_id: str, seconds_lost: float | None) -> Finding:
    return Finding(
        id=finding_id,
        title="Title",
        detail="Detail",
        confidence=Confidence.MEASURED,
        seconds_lost=seconds_lost,
    )


def test_a_finding_without_a_confidence_badge_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Finding(id="x", title="Title", detail="Detail")  # type: ignore[call-arg]


def test_findings_rank_by_seconds_lost_descending() -> None:
    ranked = rank_findings([a_finding("small", 3.0), a_finding("big", 40.0)])
    assert [finding.id for finding in ranked] == ["big", "small"]


def test_findings_without_a_time_cost_rank_last_in_stable_order() -> None:
    ranked = rank_findings(
        [
            a_finding("untimed_first", None),
            a_finding("timed", 1.0),
            a_finding("untimed_second", None),
        ]
    )
    assert [finding.id for finding in ranked] == ["timed", "untimed_first", "untimed_second"]

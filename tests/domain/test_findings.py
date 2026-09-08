# ABOUTME: Behaviour tests for the finding type and its ranking.
# ABOUTME: The confidence badge is mandatory, so its absence must be an error.

import pytest
from pydantic import ValidationError

from wowperf.domain.findings import Confidence, Finding, quantifier_for, rank_findings


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


@pytest.mark.parametrize(
    ("matching", "total", "expected"),
    [
        (5, 5, "every"),
        (4, 5, "most"),
        (3, 5, "most"),
        (2, 5, "some"),
        (1, 5, "some"),
        (2, 4, "about half"),
        (3, 4, "most"),
        # A sample every member of which disagreed is still an aggregate, and
        # "none" is the word for it. Only an empty sample has nothing to say.
        (0, 5, "none"),
        (1, 0, ""),
        (0, 0, ""),
    ],
)
def test_the_quantifier_reads_the_ratio(matching: int, total: int, expected: str) -> None:
    assert quantifier_for(matching, total) == expected


def test_a_finding_carries_no_quantifier_unless_it_is_given_one() -> None:
    finding = Finding(
        id="compare.route.skipped.0",
        title="4 of 5 fast runs skipped the pack at pull 7",
        detail="",
        confidence=Confidence.MEASURED,
    )
    assert finding.quantifier == ""

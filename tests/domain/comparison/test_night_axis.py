# ABOUTME: Behaviour tests for parse_axis_not_drawn -- the night page's one disclosure that it
# ABOUTME: draws no parse axis at all, for a reason distinct from the raid page's wipe withholding.

from wowperf.domain.comparison.night_axis import (
    NOT_DRAWN_DETAIL,
    NOT_DRAWN_ID,
    parse_axis_not_drawn,
)
from wowperf.domain.comparison.parse_axis import WITHHELD_DETAIL
from wowperf.domain.findings import Confidence


def test_the_disclosure_gives_the_right_reason_and_not_the_wipe_one() -> None:
    finding = parse_axis_not_drawn()
    assert finding.id == "compare.parse.not_drawn"
    assert finding.confidence is Confidence.MEASURED
    assert finding.seconds_lost is None
    # The reason must be this command's, never the wipe's: a night page omits the
    # axis on kills too, so borrowing that sentence would state a false cause.
    assert "did not kill the boss" not in finding.detail
    assert finding.detail != WITHHELD_DETAIL
    # Every family it stands in for, named where the reader meets the absence.
    for family in ("damage", "casts a minute", "talents", "uptime", "percentile"):
        assert family in finding.detail
    assert "wowperf raid --fight" in finding.detail


def test_the_disclosure_uses_the_module_constants() -> None:
    finding = parse_axis_not_drawn()
    assert finding.id == NOT_DRAWN_ID
    assert finding.detail == NOT_DRAWN_DETAIL
    assert finding.title

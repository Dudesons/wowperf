# ABOUTME: Behaviour tests for parse_axis_not_drawn -- the night page's one disclosure that it
# ABOUTME: draws no parse axis at all, for a reason distinct from the raid page's wipe withholding.

from wowperf.domain.comparison.night_axis import (
    NOT_DRAWN_DETAIL,
    NOT_DRAWN_ID,
    NOT_DRAWN_PACE_DETAIL,
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
    assert finding.title == "No comparison against other kills is drawn on this page"


def test_a_night_that_compared_pace_says_it_draws_no_parse_comparison_only() -> None:
    """A night handed a pace sample asked a leaderboard for its reference kills,
    so "no comparison against other kills" and "never asks a leaderboard" would
    both be false on it. The parse half of the sentence stays true and stays.
    """
    finding = parse_axis_not_drawn(pace_compared=True)
    assert finding.id == NOT_DRAWN_ID
    assert finding.confidence is Confidence.MEASURED
    assert finding.title == "No parse comparison is drawn on this page"
    assert finding.detail == NOT_DRAWN_PACE_DETAIL
    assert "never asks a leaderboard" not in finding.detail
    assert "never asks a parse leaderboard" in finding.detail
    assert "damage pace against the execution leaderboard's kills" in finding.detail
    for family in ("damage", "casts a minute", "talents", "uptime", "percentile"):
        assert family in finding.detail
    assert "wowperf raid --fight" in finding.detail
    assert finding.evidence == ("wowperf night never queries a parse leaderboard",)

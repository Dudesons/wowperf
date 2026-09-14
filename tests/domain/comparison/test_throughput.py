# ABOUTME: Behaviour tests for compare_rank, the raid percentile stated as triage.
# ABOUTME: The interesting cases are a metric gap, agreement, a wipe, and an absent player.

from wowperf.domain.comparison.raid_reference import RankedPlayer, ReportRankings
from wowperf.domain.comparison.throughput import compare_rank
from wowperf.domain.findings import Confidence


def standing(rank_percent: int, bracket_percent: int, amount: float) -> ReportRankings:
    return ReportRankings(
        fight_id=2, difficulty=4, partition=1, size=20, kill=True,
        players=(RankedPlayer(
            character_name="Emberkin", class_name="Evoker", spec="Devastation", role="dps",
            amount=amount, rank="~12", best="~9", rank_percent=rank_percent,
            bracket_percent=bracket_percent, total_parses=31004,
        ),),
    )


def test_the_percentile_states_both_metrics_and_names_itself_as_triage() -> None:
    findings = compare_rank(standing(96, 94, 247358.0), standing(71, 68, 167000.0), "Emberkin")
    assert len(findings) == 1
    one = findings[0]
    assert one.id == "compare.rank"
    assert one.confidence is Confidence.MEASURED
    assert one.seconds_lost is None
    values = {fact.label: fact.value for fact in one.facts}
    assert "96" in values["All damage"]
    assert "71" in values["Boss damage only"]
    # The constraint master design 6.7 puts on this finding, in the finding's own words.
    assert "what" in one.detail and "triage" in one.detail.lower()


def test_a_gap_between_the_two_percentiles_is_what_the_title_says() -> None:
    """96th on all damage and 71st on boss damage is the padding signal the
    side-by-side pair exists to show. A title naming only one hides it."""
    findings = compare_rank(standing(96, 94, 247358.0), standing(71, 68, 167000.0), "Emberkin")
    title = findings[0].title
    assert "96" in title and "71" in title


def test_two_percentiles_that_agree_are_said_once() -> None:
    findings = compare_rank(standing(96, 94, 247358.0), standing(96, 94, 167000.0), "Emberkin")
    assert "96" in findings[0].title
    assert findings[0].title.count("96") == 1


def test_no_percentile_is_printed_for_an_attempt_that_did_not_kill() -> None:
    """Design 14 item 7: a wipe returns no rankings row at all. Silence would
    read as a clean result, so the finding says why instead."""
    findings = compare_rank(None, None, "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.rank.unavailable"
    assert "did not kill" in findings[0].detail
    assert findings[0].seconds_lost is None


def test_a_player_absent_from_the_rankings_row_is_not_given_a_rank_of_zero() -> None:
    findings = compare_rank(standing(96, 94, 247358.0), None, "Stonewake")
    assert findings[0].id == "compare.rank.unavailable"
    assert "0" not in findings[0].title

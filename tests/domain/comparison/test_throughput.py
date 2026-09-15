# ABOUTME: Behaviour tests for compare_rank, the raid percentile stated as triage.
# ABOUTME: The interesting cases are a metric gap, agreement, a wipe, and an absent player.

from wowperf.domain.comparison.raid_reference import RaidParseRow, RankedPlayer, ReportRankings
from wowperf.domain.comparison.throughput import compare_damage_total, compare_rank
from wowperf.domain.findings import Confidence


def standing(
    rank_percent: int, bracket_percent: int, amount: float, total_parses: int = 31004
) -> ReportRankings:
    return ReportRankings(
        fight_id=2, difficulty=4, partition=1, size=20, kill=True,
        players=(RankedPlayer(
            character_name="Emberkin", class_name="Evoker", spec="Devastation", role="dps",
            amount=amount, rank="~12", best="~9", rank_percent=rank_percent,
            bracket_percent=bracket_percent, total_parses=total_parses,
        ),),
    )


def test_the_percentile_states_both_metrics_and_names_itself_as_triage() -> None:
    # dps and bossdps are different boards (measured 2026-09-14) and hold different
    # reports, so the two standings are given different total_parses on purpose: a
    # "Boss damage only" fact that quietly read the dps standing's parse count would
    # still pass every other assertion here.
    findings = compare_rank(
        standing(96, 94, 247358.0, total_parses=31004),
        standing(71, 68, 167000.0, total_parses=18422),
        "Emberkin",
        "Emberkin",
    )
    assert len(findings) == 1
    one = findings[0]
    assert one.id == "compare.rank"
    assert one.confidence is Confidence.MEASURED
    assert one.seconds_lost is None
    values = {fact.label: fact.value for fact in one.facts}
    assert "96" in values["All damage"] and "31004" in values["All damage"]
    assert "71" in values["Boss damage only"] and "18422" in values["Boss damage only"]
    # The constraint master design 6.7 puts on this finding, in the finding's own words.
    assert "what" in one.detail and "triage" in one.detail.lower()


def test_a_gap_between_the_two_percentiles_is_what_the_title_says() -> None:
    """96th on all damage and 71st on boss damage is the padding signal the
    side-by-side pair exists to show. A title naming only one hides it."""
    findings = compare_rank(
        standing(96, 94, 247358.0, total_parses=31004),
        standing(71, 68, 167000.0, total_parses=18422),
        "Emberkin",
        "Emberkin",
    )
    title = findings[0].title
    assert "96" in title and "71" in title


def test_two_percentiles_that_agree_are_said_once() -> None:
    findings = compare_rank(
        standing(96, 94, 247358.0, total_parses=31004),
        standing(96, 94, 167000.0, total_parses=18422),
        "Emberkin",
        "Emberkin",
    )
    assert "96" in findings[0].title
    assert findings[0].title.count("96") == 1


def test_no_percentile_is_printed_for_an_attempt_that_did_not_kill() -> None:
    """Design 14 item 7: a wipe returns no rankings row at all. Silence would
    read as a clean result, so the finding says why instead."""
    findings = compare_rank(None, None, "Emberkin", "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.rank.unavailable"
    assert "did not kill" in findings[0].detail
    assert findings[0].seconds_lost is None


def test_a_player_absent_from_the_rankings_row_is_not_given_a_rank_of_zero() -> None:
    findings = compare_rank(standing(96, 94, 247358.0), None, "Stonewake", "Stonewake")
    assert findings[0].id == "compare.rank.unavailable"
    assert "0" not in findings[0].title


def test_a_disambiguated_display_name_is_not_what_the_rankings_row_is_joined_on() -> None:
    """A rankings row carries a plain character name, and two roster members
    sharing one is ordinary in a raid. The name a reader is shown tells them
    apart; the name this row is found by cannot, so the two are separate
    arguments and only one of them reaches the join."""
    findings = compare_rank(
        standing(96, 94, 247358.0), None, "Emberkin (actor 7)", "Emberkin"
    )

    assert findings[0].id == "compare.rank"
    assert "96th percentile" in findings[0].title
    assert findings[0].title.startswith("Emberkin (actor 7) ranks")


def board(*amounts: float) -> tuple[RaidParseRow, ...]:
    return tuple(
        RaidParseRow(
            report_code=f"code{i:012d}", fight_id=i, duration_ms=300_000 + i * 1000,
            character_name="Stonewake", class_name="Evoker", spec="Devastation",
            amount=amount, size=25 + i,
        )
        for i, amount in enumerate(amounts)
    )


def ranked(amount: float) -> RankedPlayer:
    return RankedPlayer(
        character_name="Emberkin", class_name="Evoker", spec="Devastation", role="dps",
        amount=amount, rank="~12", best="~9", rank_percent=96, bracket_percent=94,
        total_parses=31004,
    )


def test_our_rate_is_compared_against_the_board_median_without_dividing_anything() -> None:
    """Both sides are already per-second rates -- measured 2026-09-14. The median
    of 100, 200, 300, 400, 500 is 300, and none of the five is 300, so a
    mutation that picks a row instead of the median cannot pass."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    assert len(findings) == 1
    values = {fact.label: fact.value for fact in findings[0].facts}
    assert "300" in values["All damage"]
    assert "150" in values["All damage"]
    assert "150" in values["Boss damage only"]
    assert "90" in values["Boss damage only"]


def test_a_player_above_one_median_and_below_the_other_is_told_so() -> None:
    """The signal the side-by-side pair exists for: ahead on everything, behind
    on the boss, means damage went into adds."""
    findings = compare_damage_total(
        ranked(400.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    title = findings[0].title.lower()
    assert "above" in title and "below" in title


def test_the_observed_range_is_stated_and_is_not_the_median() -> None:
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0),
        board(100.0, 200.0, 300.0, 400.0, 500.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    evidence = " ".join(findings[0].evidence)
    assert "100" in evidence and "500" in evidence


def test_only_the_first_five_of_a_longer_board_are_counted() -> None:
    """SAMPLE_SIZE is 5 everywhere else in this codebase and is 5 here."""
    long_board = board(100.0, 200.0, 300.0, 400.0, 500.0, 10_000.0, 20_000.0)
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), long_board, long_board, "Emberkin"
    )
    values = {fact.label: fact.value for fact in findings[0].facts}
    assert "300" in values["All damage"]
    assert "10" not in values["All damage"].replace("300", "")


def test_two_references_fall_back_to_a_single_one_and_say_so() -> None:
    """Below the floor the figure is one reference's own, not a median of two.

    The note alone cannot say that: it fires off the eligible count and is
    appended whether the fallback ran or not, so a card stating the median of
    both references -- 150.0 on the all-damage board, which is also its mean --
    would carry the note unchanged and read as a single reference while being
    an aggregate of two. The two amounts on each board therefore differ, so
    the figure the fallback produces is not the figure it replaced.
    """
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), board(100.0, 200.0), board(50.0, 100.0), "Emberkin"
    )
    values = {fact.label: fact.value for fact in findings[0].facts}

    assert values["All damage"] == "150.0 against a single reference's 100.0"
    assert values["Boss damage only"] == "90.0 against a single reference's 50.0"
    assert "all damage range 100.0 to 100.0 over 1 reference" in findings[0].evidence
    assert "boss damage range 50.0 to 50.0 over 1 reference" in findings[0].evidence
    assert any("a single reference, not an aggregate" in note for note in findings[0].evidence)


def test_below_the_floor_no_sentence_on_the_card_claims_an_aggregate() -> None:
    """The evidence says "a single reference, not an aggregate"; a title above it
    reading "the sample median" contradicts it on the same card.

    Every other axis that calls `too_few` changes its words below the floor --
    `compare_mechanics`, `compare_tempo`, `compare_route` and `compare_spells`
    each hand off to a pairwise form worded for one reference. This one states
    its own two metrics, so it changes the nouns rather than the function, and
    the whole card is swept because the contradiction was a title and a fact
    disagreeing with an evidence line beneath them.
    """
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), board(100.0, 200.0), board(50.0, 100.0), "Emberkin"
    )
    one = findings[0]

    assert one.title == (
        "Emberkin sat above a single reference on both all damage and boss damage"
    )
    for line in (one.title, one.detail, *(fact.value for fact in one.facts)):
        assert "median" not in line, line


def test_one_axis_below_the_floor_leaves_the_other_one_calling_itself_a_median() -> None:
    """The two boards are drawn independently and fall below the floor
    independently, so one card can carry an aggregate and a single reference at
    once. Neither noun may be spread onto the other metric."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0),
        board(100.0),
        board(50.0, 100.0, 150.0, 200.0, 250.0),
        "Emberkin",
    )
    one = findings[0]
    values = {fact.label: fact.value for fact in one.facts}

    assert one.title == (
        "Emberkin sat below the sample median on boss damage while above a single "
        "reference on all damage"
    )
    assert values["All damage"] == "150.0 against a single reference's 100.0"
    assert values["Boss damage only"] == "90.0 against a median of 150.0"


def test_no_damage_comparison_is_printed_for_an_attempt_that_did_not_kill() -> None:
    findings = compare_damage_total(None, None, (), (), "Emberkin")
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.total.unavailable"
    assert "did not kill" in findings[0].detail


def test_an_empty_all_damage_board_leaves_the_comparison_unavailable() -> None:
    """A kill can still leave the all-damage leaderboard empty -- a thin sample
    for an uncommon spec, or a fetch that came back with nothing. That is a
    different reason than a wipe, and the wording must say so: not "did not
    kill", because this attempt did."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), (), board(50.0, 100.0, 150.0), "Emberkin"
    )
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.total.unavailable"
    assert "did not kill" not in findings[0].detail
    assert "all damage" in findings[0].detail.lower()


def test_an_empty_boss_damage_board_leaves_the_comparison_unavailable() -> None:
    """The reverse of the above: the all-damage board is fine, the boss-only
    board came back empty. Either alone must withhold the whole comparison."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), board(100.0, 200.0, 300.0), (), "Emberkin"
    )
    assert len(findings) == 1
    assert findings[0].id == "compare.damage.total.unavailable"
    assert "did not kill" not in findings[0].detail
    assert "boss damage" in findings[0].detail.lower()


def test_two_axes_below_floor_with_different_counts_are_each_labelled() -> None:
    """1 eligible all-damage row and 2 eligible boss-damage rows must not
    collapse into indistinguishable notes -- a reader needs to know which
    count belongs to which metric."""
    findings = compare_damage_total(
        ranked(150.0), ranked(90.0), board(100.0), board(50.0, 100.0), "Emberkin"
    )
    evidence = " ".join(findings[0].evidence)
    assert (
        "all damage: a single reference, not an aggregate: 1 of the sample was comparable"
        in evidence
    )
    assert (
        "boss damage: a single reference, not an aggregate: 2 of the sample were comparable"
        in evidence
    )

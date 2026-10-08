# ABOUTME: Boss debuff uptime against the parse sample: the buff family's thresholds, debuff words.
# ABOUTME: Pins the gap, level, unjudged, the pairwise fallback and every unavailable branch.

import pytest

from tests.domain.comparison.test_boss_debuffs import (
    BOSS_PULL,
    OTHER,
    PLAYER,
    RUN_PLAYERS,
    a_log,
    held,
)
from tests.domain.comparison.test_uptime import BOSS, a_player, a_run
from wowperf.domain.auras import Aura, AuraBand
from wowperf.domain.comparison.boss_debuffs import (
    BossDebuffs,
    BossWindow,
    Withheld,
    boss_debuffs,
)
from wowperf.domain.comparison.debuff_uptime import (
    boss_debuff_table,
    compare_boss_debuffs_sample,
)
from wowperf.domain.comparison.measures import BossCell, Verdict
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.debuffs import PairingTally
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

OUR_NAME = "Stonewake (actor 7)"
DOT, DOT_NAME = 55078, "Blood Plague"
REFERENCE_NAMES = ("Bríala", "Кириллица", "Emberkin")


def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> BossDebuffs:
    """One measured boss pull of `seconds`, each debuff on it for its share from the pull."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001, name="The Test Colossus", start_ms=0, end_ms=end_ms, boss_game_id=5000
    )
    auras = tuple(
        Aura(
            ability_id=ability_id,
            name=name,
            total_uptime_ms=int(end_ms * share),
            uses=1,
            bands=(AuraBand(start_ms=0, end_ms=int(end_ms * share)),),
        )
        for ability_id, name, share in shares
        if share > 0
    )
    return BossDebuffs(windows=(window,), auras=auras)


def a_member(name: str, debuffs: BossDebuffs | None) -> ParseMember:
    return ParseMember(
        character_name=name, report_code="ref", fight_id=1, boss_seconds=100.0, boss_debuffs=debuffs
    )


def a_sample(*shares: float) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, on_the_boss((DOT, DOT_NAME, share)))
            for name, share in zip(REFERENCE_NAMES, shares, strict=False)
        )
    )


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_debuff_kept_up_well_below_the_sample_is_a_gap() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(
            on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
        )
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.confidence is Confidence.DERIVED
    assert gap.title == (
        "Blood Plague was on the boss a median 90% of boss time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "range 90% to 90% across 3 top parses" in gap.evidence
    assert (
        "A council pull, or a pull with no single boss, is left out on both sides."
        in gap.detail
    )
    assert "0 of 3 references had no debuff data" in gap.evidence
    assert (gap.ability_id, gap.ability_name) == (DOT, DOT_NAME)


def test_a_narrow_difference_is_level_and_reports_nothing() -> None:
    findings = compare_boss_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
    )

    assert findings == []


def test_a_debuff_the_sample_kept_and_we_never_applied_is_named_not_judged() -> None:
    findings = by_id(compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9, 0.9)))

    assert set(findings) == {"compare.uptime.boss.unjudged"}
    assert findings["compare.uptime.boss.unjudged"].evidence[0] == DOT_NAME


def test_below_the_floor_one_reference_is_stated_pairwise() -> None:
    findings = by_id(
        compare_boss_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9))
    )

    gap = findings["compare.uptime.boss.0"]
    assert gap.title == (
        "Blood Plague was on the boss for 90% of Bríala's boss time, 50% of Stonewake (actor 7)'s"
    )
    assert gap.evidence[-1].startswith("a single reference, not an aggregate")


def test_below_the_floor_a_narrow_difference_is_not_a_gap() -> None:
    findings = compare_boss_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9)
    )

    assert findings == []


def test_below_the_floor_a_debuff_we_never_applied_is_passed_over() -> None:
    findings = compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9))

    assert findings == []


def test_an_empty_sample_says_nothing_here() -> None:
    assert compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, ParseSample()) == []


def test_no_reference_with_debuff_data_is_unavailable() -> None:
    sample = ParseSample(members=(a_member("Bríala", None), a_member("Кириллица", None)))

    [finding] = compare_boss_debuffs_sample(on_the_boss(), OUR_NAME, sample)

    assert finding.id == "compare.uptime.boss.unavailable"
    assert finding.confidence is Confidence.MEASURED
    assert "0 of 2 references returned debuff data" in finding.evidence


def test_our_own_missing_stream_is_unavailable() -> None:
    [finding] = compare_boss_debuffs_sample(None, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our debuff data absent" in finding.evidence


def test_a_run_whose_every_boss_was_withheld_is_unavailable() -> None:
    council = BossDebuffs(
        windows=(
            BossWindow(
                encounter_id=2001,
                name="The Twin Council",
                start_ms=0,
                end_ms=60_000,
                withheld=Withheld.COUNCIL,
            ),
        )
    )

    [finding] = compare_boss_debuffs_sample(council, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.boss.unavailable"
    assert "our measured boss time 0s" in finding.evidence


def test_at_most_five_gaps_are_reported() -> None:
    six = tuple((DOT + offset, f"Debuff {offset}", 0.9) for offset in range(6))
    ours = tuple((ability_id, name, 0.3) for ability_id, name, _ in six)
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*six)) for name in REFERENCE_NAMES)
    )

    findings = compare_boss_debuffs_sample(on_the_boss(*ours), OUR_NAME, sample)

    assert sorted(finding.id for finding in findings) == [
        f"compare.uptime.boss.{rank}" for rank in range(5)
    ]


def test_the_service_files_the_gap_under_the_players_own_slug() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample(0.9, 0.9, 0.9),
        our_boss_debuffs=on_the_boss((DOT, DOT_NAME, 0.5)),
    )

    ids = [finding.id for finding in compare(LoadedRun(run=a_run(BOSS)), None, [subject])]

    assert "compare.uptime.boss.0.stonewake-0" in ids


FIRST = BossWindow(
    encounter_id=2001, name="First Boss", start_ms=0, end_ms=100_000, boss_game_id=5000
)
SECOND = BossWindow(
    encounter_id=2002,
    name="Second Boss",
    start_ms=200_000,
    end_ms=300_000,
    boss_game_id=6000,
)
SECOND_COUNCIL = SECOND.model_copy(update={"boss_game_id": None, "withheld": Withheld.COUNCIL})


def on_two_bosses(
    first: float, second: float, *, windows: tuple[BossWindow, ...] = (FIRST, SECOND)
) -> BossDebuffs:
    bands = []
    if first > 0:
        bands.append(AuraBand(start_ms=0, end_ms=int(100_000 * first)))
    if second > 0:
        bands.append(AuraBand(start_ms=200_000, end_ms=200_000 + int(100_000 * second)))
    auras = (
        (
            Aura(
                ability_id=DOT,
                name=DOT_NAME,
                total_uptime_ms=0,
                uses=len(bands),
                bands=tuple(bands),
            ),
        )
        if bands
        else ()
    )
    return BossDebuffs(windows=windows, auras=auras)


def a_two_boss_sample(*members: BossDebuffs) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, debuffs)
            for name, debuffs in zip(REFERENCE_NAMES, members, strict=True)
        )
    )


def test_a_row_carries_the_overall_verdict_and_one_cell_per_boss() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    [row] = table.rows
    assert row.uptime.verdict is Verdict.BELOW
    assert row.cells == (
        BossCell(encounter_id=2001, boss="First Boss", ours=0.5, their_median=0.9),
        BossCell(encounter_id=2002, boss="Second Boss", ours=0.9, their_median=0.9),
    )
    assert (table.bosses, table.seconds) == (("First Boss", "Second Boss"), 200.0)


def test_a_boss_fought_twice_is_one_column_and_one_cell_summed_over_both_pulls() -> None:
    # A wipe, then the kill: two windows sharing one encounter id. 50s of the
    # first pull's 100s and 90s of the second's make 140s of 200s.
    kill = FIRST.model_copy(update={"start_ms": 200_000, "end_ms": 300_000})
    sample = a_two_boss_sample(
        *(on_two_bosses(0.9, 0.9, windows=(FIRST, kill)) for _ in range(3))
    )

    table = boss_debuff_table(on_two_bosses(0.5, 0.9, windows=(FIRST, kill)), sample)

    assert table.bosses == ("First Boss",)
    assert table.seconds == 200.0
    [row] = table.rows
    [cell] = row.cells
    assert cell.encounter_id == 2001
    assert cell.ours == pytest.approx(0.7)
    assert cell.their_median == pytest.approx(0.9)


def test_our_council_cell_is_withheld_with_its_reason() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(
        on_two_bosses(0.5, 0.0, windows=(FIRST, SECOND_COUNCIL)), sample
    )

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", withheld=Withheld.COUNCIL
    )


def test_a_boss_no_reference_reached_shows_ours_and_says_so() -> None:
    sample = a_two_boss_sample(
        *(on_two_bosses(0.9, 0.0, windows=(FIRST,)) for _ in range(3))
    )

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.NOT_REACHED
    )


def test_a_boss_too_few_references_applied_it_on_shows_ours_and_says_so() -> None:
    sample = a_two_boss_sample(
        on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.0)
    )

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.TOO_FEW
    )


def test_no_table_below_the_floor_or_without_our_own_figure() -> None:
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )
    three = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert boss_debuff_table(on_two_bosses(0.5, 0.9), two).rows == ()
    assert boss_debuff_table(None, three).rows == ()


def test_our_own_pairing_tally_rides_on_the_table() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = on_two_bosses(0.5, 0.9).model_copy(
        update={"tally": PairingTally(orphan_removes=2, closed_at_end=1)}
    )

    assert boss_debuff_table(ours, sample).tally == PairingTally(
        orphan_removes=2, closed_at_end=1
    )


def a_tallied_run() -> BossDebuffs:
    return on_two_bosses(0.5, 0.9).model_copy(
        update={"tally": PairingTally(orphan_removes=2, closed_at_end=1)}
    )


def test_below_the_floor_the_empty_table_still_carries_our_own_tally_and_seconds() -> None:
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )

    table = boss_debuff_table(a_tallied_run(), two)

    assert table.rows == ()
    assert table.seconds == 200.0
    assert table.tally == PairingTally(orphan_removes=2, closed_at_end=1)


def test_with_no_measured_boss_the_empty_table_still_carries_our_own_tally() -> None:
    council = BossDebuffs(
        windows=(
            BossWindow(
                encounter_id=2001,
                name="The Twin Council",
                start_ms=0,
                end_ms=60_000,
                withheld=Withheld.COUNCIL,
            ),
        ),
        tally=PairingTally(orphan_removes=3),
    )
    three = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(council, three)

    assert table.rows == ()
    assert table.seconds == 0.0
    assert table.tally == PairingTally(orphan_removes=3)


def test_a_clean_log_records_a_zero_tally_not_an_absent_one() -> None:
    two = ParseSample(members=(a_member("Bríala", on_two_bosses(0.9, 0.9)),))

    table = boss_debuff_table(on_two_bosses(0.5, 0.9), two)

    assert table.tally == PairingTally()
    assert table.tally is not None


def test_when_our_stream_could_not_be_read_the_table_records_no_tally() -> None:
    three = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = boss_debuff_table(None, three)

    assert table.tally is None
    assert table.seconds == 0.0


TEAMMATE, SECOND_TEAMMATE = 702, 703


def shared_with(debuffs: BossDebuffs, ability_id: int, *owners: int) -> BossDebuffs:
    return debuffs.model_copy(update={"shared_with": ((ability_id, owners),)})


def test_a_shared_debuff_far_below_the_sample_is_not_a_gap() -> None:
    ours = shared_with(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_boss_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_below_the_floor_a_shared_debuff_is_not_a_gap_either() -> None:
    ours = shared_with(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_boss_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9)) == []


def test_a_shared_debuff_we_never_applied_is_not_named_unjudged() -> None:
    ours = shared_with(on_the_boss(), DOT, TEAMMATE, SECOND_TEAMMATE)

    assert compare_boss_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


OTHER_DOT, OTHER_DOT_NAME = 55095, "Frost Fever"


def test_only_the_shared_debuff_is_set_aside() -> None:
    both = ((DOT, DOT_NAME, 0.9), (OTHER_DOT, OTHER_DOT_NAME, 0.9))
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*both)) for name in REFERENCE_NAMES)
    )
    ours = shared_with(
        on_the_boss((DOT, DOT_NAME, 0.3), (OTHER_DOT, OTHER_DOT_NAME, 0.3)), DOT, TEAMMATE
    )

    findings = compare_boss_debuffs_sample(ours, OUR_NAME, sample)

    assert [(finding.id, finding.ability_id) for finding in findings] == [
        ("compare.uptime.boss.0", OTHER_DOT)
    ]


def test_a_teammate_taking_the_debuff_over_from_us_leaves_no_gap() -> None:
    # Read off a log: ours 10s of the 60s pull, the teammate's the other 50s,
    # never at once. The sample's 90% against our 17% would be a gap.
    ours = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 20_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert compare_boss_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_a_teammates_copy_beside_ours_leaves_the_gap_standing() -> None:
    # The same figures, but the teammate's copy sat on the boss beside ours, so
    # theirs took nothing away from ours: the gap is ours.
    ours = boss_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 10_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    findings = compare_boss_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert [finding.id for finding in findings] == ["compare.uptime.boss.0"]


def test_a_shared_row_keeps_its_figures_and_names_who_it_was_shared_with() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = shared_with(on_two_bosses(0.5, 0.9), DOT, TEAMMATE, SECOND_TEAMMATE)

    [row] = boss_debuff_table(ours, sample).rows

    assert row.shared_with == (TEAMMATE, SECOND_TEAMMATE)
    assert row.uptime.ours == pytest.approx(0.7)
    assert row.uptime.verdict is Verdict.BELOW


def test_a_row_whose_debuff_is_not_the_shared_one_names_nobody() -> None:
    sample = a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = shared_with(on_two_bosses(0.5, 0.9), OTHER_DOT, TEAMMATE)

    [row] = boss_debuff_table(ours, sample).rows

    assert row.shared_with == ()


def test_the_players_measures_carry_the_debuff_table() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_two_boss_sample(*(on_two_bosses(0.9, 0.9) for _ in range(3))),
        our_boss_debuffs=on_two_bosses(0.5, 0.9),
    )

    measures = comparison_measures(LoadedRun(run=a_run(BOSS)), [subject])

    assert [row.uptime.name for row in measures["stonewake-0"].boss_debuffs.rows] == [DOT_NAME]

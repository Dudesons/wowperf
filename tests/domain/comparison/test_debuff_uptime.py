# ABOUTME: Debuff coverage against the parse sample: the buff family's thresholds, on Overall.
# ABOUTME: Pins the gap, level, unjudged, the pairwise fallback, the stretch cells and reach.

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
from wowperf.domain.comparison.boss_debuffs import BossDebuffs, BossTarget, BossWindow, Withheld
from wowperf.domain.comparison.debuff_uptime import compare_debuffs_sample, debuff_table
from wowperf.domain.comparison.key_debuffs import KeyDebuffs, StretchCover, key_debuffs
from wowperf.domain.comparison.measures import BossCell, DebuffReach, StretchCell, Verdict
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.service import ComparisonSubject, compare
from wowperf.domain.comparison.tables import comparison_measures
from wowperf.domain.debuffs import PairingTally
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun

OUR_NAME = "Stonewake (actor 7)"
DOT, DOT_NAME = 55078, "Blood Plague"
REFERENCE_NAMES = ("Bríala", "Кириллица", "Emberkin")


def on_the_boss(*shares: tuple[int, str, float], seconds: float = 100.0) -> KeyDebuffs:
    """One measured boss pull of `seconds` and no other enemy, each debuff on it for its share."""
    end_ms = int(seconds * 1000)
    window = BossWindow(
        encounter_id=2001,
        name="The Test Colossus",
        start_ms=0,
        end_ms=end_ms,
        targets=(BossTarget(game_id=5000, start_ms=0, end_ms=end_ms),),
    )
    carried = [(ability_id, name, share) for ability_id, name, share in shares if share > 0]
    return KeyDebuffs(
        bosses=BossDebuffs(
            windows=(window,),
            covered=tuple(
                (2001, ability_id, int(end_ms * share)) for ability_id, _, share in carried
            ),
            names=tuple((ability_id, name) for ability_id, name, _ in carried),
            reached=tuple((ability_id, 1) for ability_id, _, _ in carried),
        )
    )


def with_trash(
    debuffs: KeyDebuffs,
    share: float,
    *,
    lives: int = 4,
    reached: int = 4,
    seconds: float = 100.0,
) -> KeyDebuffs:
    """The same key with trash beside its bosses: `lives` mobs alive `seconds` in all,
    the debuff on them for `share` of that time and on `reached` of them."""
    alive_ms = int(seconds * 1000)
    carried = share > 0
    return debuffs.model_copy(
        update={
            "trash": StretchCover(
                lives=lives,
                alive_ms=alive_ms,
                covered=((DOT, int(alive_ms * share)),) if carried else (),
                reached=((DOT, reached),) if carried else (),
            ),
            "life_names": ((DOT, DOT_NAME),) if carried else (),
        }
    )


def on_its_bosses(debuffs: KeyDebuffs, **fields: object) -> KeyDebuffs:
    """The same key with these fields of its boss figure replaced."""
    return debuffs.model_copy(update={"bosses": debuffs.bosses.model_copy(update=fields)})


def a_member(name: str, debuffs: KeyDebuffs | None) -> ParseMember:
    return ParseMember(
        character_name=name, report_code="ref", fight_id=1, boss_seconds=100.0, debuffs=debuffs
    )


def a_sample(*shares: float) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, on_the_boss((DOT, DOT_NAME, share)))
            for name, share in zip(REFERENCE_NAMES, shares, strict=False)
        )
    )


def a_sample_of(*members: KeyDebuffs) -> ParseSample:
    return ParseSample(
        members=tuple(
            a_member(name, debuffs)
            for name, debuffs in zip(REFERENCE_NAMES, members, strict=True)
        )
    )


def by_id(findings: list[Finding]) -> dict[str, Finding]:
    return {finding.id: finding for finding in findings}


def test_a_debuff_kept_up_well_below_the_sample_is_a_gap() -> None:
    findings = by_id(
        compare_debuffs_sample(
            on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
        )
    )

    gap = findings["compare.uptime.debuff.0"]
    assert gap.confidence is Confidence.DERIVED
    assert gap.title == (
        "Blood Plague covered a median 90% of enemy-alive time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "range 90% to 90% across 3 top parses" in gap.evidence
    assert "ours over 100s of measured enemy-alive time" in gap.evidence
    assert "a trash mob from the first debuff anyone put on it to its death" in gap.detail
    assert (
        "a council's bosses each from the pull's start to their own death, or to the pull's "
        "end if they did not die there."
    ) in gap.detail
    assert "0 of 3 references had no debuff data" in gap.evidence
    assert (gap.ability_id, gap.ability_name) == (DOT, DOT_NAME)


def test_a_narrow_difference_is_level_and_reports_nothing() -> None:
    findings = compare_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9, 0.9)
    )

    assert findings == []


def test_a_debuff_the_sample_kept_and_we_never_applied_is_named_not_judged() -> None:
    findings = by_id(compare_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9, 0.9)))

    assert set(findings) == {"compare.uptime.debuff.unjudged"}
    unjudged = findings["compare.uptime.debuff.unjudged"]
    assert unjudged.title == (
        "1 debuff the sample kept on enemies is absent for Stonewake (actor 7)"
    )
    assert unjudged.evidence[0] == DOT_NAME


def test_below_the_floor_one_reference_is_stated_pairwise() -> None:
    findings = by_id(
        compare_debuffs_sample(on_the_boss((DOT, DOT_NAME, 0.5)), OUR_NAME, a_sample(0.9, 0.9))
    )

    gap = findings["compare.uptime.debuff.0"]
    assert gap.title == (
        "Blood Plague covered 90% of Bríala's enemy-alive time, 50% of Stonewake (actor 7)'s"
    )
    assert gap.evidence[-1].startswith("a single reference, not an aggregate")


def test_below_the_floor_a_narrow_difference_is_not_a_gap() -> None:
    findings = compare_debuffs_sample(
        on_the_boss((DOT, DOT_NAME, 0.85)), OUR_NAME, a_sample(0.9, 0.9)
    )

    assert findings == []


def test_below_the_floor_a_debuff_we_never_applied_is_passed_over() -> None:
    findings = compare_debuffs_sample(on_the_boss(), OUR_NAME, a_sample(0.9, 0.9))

    assert findings == []


def test_an_empty_sample_says_nothing_here() -> None:
    assert compare_debuffs_sample(on_the_boss(), OUR_NAME, ParseSample()) == []


def test_no_reference_with_debuff_data_is_unavailable() -> None:
    sample = ParseSample(members=(a_member("Bríala", None), a_member("Кириллица", None)))

    [finding] = compare_debuffs_sample(on_the_boss(), OUR_NAME, sample)

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert finding.title == "Debuff coverage could not be compared for Stonewake (actor 7)"
    assert finding.confidence is Confidence.MEASURED
    assert "0 of 2 references returned debuff data" in finding.evidence


def test_our_own_missing_stream_is_unavailable() -> None:
    [finding] = compare_debuffs_sample(None, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert "our debuff data absent" in finding.evidence


def test_a_key_with_no_enemy_measured_is_unavailable() -> None:
    unfound = KeyDebuffs(
        bosses=BossDebuffs(
            windows=(
                BossWindow(
                    encounter_id=2001,
                    name="The Fixture Hall",
                    start_ms=0,
                    end_ms=60_000,
                    withheld=Withheld.NO_BOSS,
                ),
            )
        )
    )

    [finding] = compare_debuffs_sample(unfound, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert finding.id == "compare.uptime.debuff.unavailable"
    assert "our measured enemy-alive time 0s" in finding.evidence


def test_at_most_five_gaps_are_reported() -> None:
    six = tuple((DOT + offset, f"Debuff {offset}", 0.9) for offset in range(6))
    ours = tuple((ability_id, name, 0.3) for ability_id, name, _ in six)
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*six)) for name in REFERENCE_NAMES)
    )

    findings = compare_debuffs_sample(on_the_boss(*ours), OUR_NAME, sample)

    assert sorted(finding.id for finding in findings) == [
        f"compare.uptime.debuff.{rank}" for rank in range(5)
    ]


def test_the_service_files_the_gap_under_the_players_own_slug() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample(0.9, 0.9, 0.9),
        our_debuffs=on_the_boss((DOT, DOT_NAME, 0.5)),
    )

    ids = [finding.id for finding in compare(LoadedRun(run=a_run(BOSS)), None, [subject])]

    assert "compare.uptime.debuff.0.stonewake-0" in ids


def test_the_verdict_reads_trash_and_bosses_summed() -> None:
    # Ours: 90% of the boss and 10% of the trash, so 50% of the key. The sample:
    # 90% of both. On the bosses alone ours would read level.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    findings = by_id(compare_debuffs_sample(ours, OUR_NAME, sample))

    gap = findings["compare.uptime.debuff.0"]
    assert gap.title == (
        "Blood Plague covered a median 90% of enemy-alive time across 3 top parses; "
        "50% for Stonewake (actor 7)"
    )
    assert "ours over 200s of measured enemy-alive time" in gap.evidence


def test_a_row_describes_its_trash_and_bosses_beside_the_verdict() -> None:
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.uptime.verdict is Verdict.BELOW
    assert row.uptime.ours == pytest.approx(0.5)
    assert row.trash == StretchCell(ours=0.1, their_median=0.9)
    assert row.bosses == StretchCell(ours=0.9, their_median=0.9)


def test_a_key_with_no_trash_measured_says_so_in_its_trash_cells() -> None:
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(on_the_boss((DOT, DOT_NAME, 0.5)), sample).rows

    assert row.trash == StretchCell(withheld=Withheld.NO_TRASH)
    assert row.reach.trash == StretchCell(withheld=Withheld.NO_TRASH)


def test_a_trash_cell_no_reference_measured_shows_ours_and_says_so() -> None:
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.5)), 0.1)
    sample = a_sample(0.9, 0.9, 0.9)

    [row] = debuff_table(ours, sample).rows

    assert row.trash == StretchCell(ours=0.1, withheld=Withheld.NOT_REACHED)


def test_reach_is_described_for_every_stretch() -> None:
    # Ours sat on the boss and on 1 of 4 mobs: 2 of 5 enemies. Each reference
    # sat on the boss and on all 4, so each of the three gives an Overall reach
    # of 1.0, and those three are what the reach table's Range and Sample state.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1, reached=1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.reach == DebuffReach(
        overall=StretchCell(ours=0.4, their_median=1.0),
        trash=StretchCell(ours=0.25, their_median=1.0),
        bosses=StretchCell(ours=1.0, their_median=1.0),
        overall_fractions=(1.0, 1.0, 1.0),
    )


def test_reach_keeps_the_references_overall_reach_not_their_coverage() -> None:
    # Each reference covered 90% of the boss and of its trash, and reached the
    # boss and 2 of its 4 mobs: 3 of 5 enemies. Their coverage, 0.9, is not
    # their reach, 0.6, and only the reach belongs under the reach table's Range.
    ours = with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.1, reached=1)
    sample = a_sample_of(
        *(with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9, reached=2) for _ in range(3))
    )

    [row] = debuff_table(ours, sample).rows

    assert row.reach.overall_fractions == (0.6, 0.6, 0.6)
    assert row.uptime.their_fractions == (0.9, 0.9, 0.9)
    # The stretches read their own reach: 2 of 4 mobs, and the one boss.
    assert row.reach.trash == StretchCell(ours=0.25, their_median=0.5)
    assert row.reach.bosses == StretchCell(ours=1.0, their_median=1.0)


def test_reach_states_only_the_references_that_reached_an_enemy() -> None:
    # Three references reached the boss and 2 of 4 mobs; a fourth carried the
    # debuff on nothing, so it was never a reference for it and is not counted
    # under the reach table's Range and Sample.
    nothing = with_trash(on_the_boss(), 0.0)
    carrying = [
        with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9, reached=2) for _ in range(3)
    ]
    sample = ParseSample(
        members=tuple(
            a_member(name, debuffs)
            for name, debuffs in zip(
                (*REFERENCE_NAMES, "Stonewake"), (*carrying, nothing), strict=True
            )
        )
    )

    [row] = debuff_table(with_trash(on_the_boss((DOT, DOT_NAME, 0.5)), 0.5), sample).rows

    assert row.reach.overall_fractions == (0.6, 0.6, 0.6)


def test_a_reference_that_measured_no_trash_is_not_counted_for_it() -> None:
    # Two references carried the debuff on trash and the third had no trash
    # life at all. That third measured nothing there, which is not a zero: it
    # does not make a third reference for the median, so the cell is too few.
    two = [with_trash(on_the_boss((DOT, DOT_NAME, 0.9)), 0.9) for _ in range(2)]
    sample = a_sample_of(*two, on_the_boss((DOT, DOT_NAME, 0.9)))

    [row] = debuff_table(with_trash(on_the_boss((DOT, DOT_NAME, 0.5)), 0.5), sample).rows

    assert row.trash == StretchCell(ours=0.5, withheld=Withheld.TOO_FEW)


def test_a_debuff_seen_only_on_trash_still_earns_a_row() -> None:
    # No one put it on the boss. The sample kept it on 90% of their trash, which
    # is 45% of the key; ours 10%, which is 5%.
    ours = with_trash(on_the_boss(), 0.1)
    sample = a_sample_of(*(with_trash(on_the_boss(), 0.9) for _ in range(3)))

    [row] = debuff_table(ours, sample).rows

    assert (row.uptime.name, row.uptime.verdict) == (DOT_NAME, Verdict.BELOW)
    assert row.uptime.ours == pytest.approx(0.05)
    assert row.uptime.their_median == pytest.approx(0.45)
    assert row.bosses == StretchCell(ours=0.0, withheld=Withheld.TOO_FEW)


def test_the_table_carries_what_could_not_be_measured() -> None:
    ours = on_the_boss((DOT, DOT_NAME, 0.5)).model_copy(
        update={"unmeasured_no_death": 3, "undebuffed_deaths": 2}
    )

    full = debuff_table(ours, a_sample(0.9, 0.9, 0.9))
    thin = debuff_table(ours, a_sample(0.9, 0.9))

    assert (full.unmeasured_no_death, full.undebuffed_deaths) == (3, 2)
    assert full.rows
    assert (thin.unmeasured_no_death, thin.undebuffed_deaths) == (3, 2)
    assert thin.rows == ()


FIRST = BossWindow(
    encounter_id=2001,
    name="First Boss",
    start_ms=0,
    end_ms=100_000,
    targets=(BossTarget(game_id=5000, start_ms=0, end_ms=100_000),),
)
SECOND = BossWindow(
    encounter_id=2002,
    name="Second Boss",
    start_ms=200_000,
    end_ms=300_000,
    targets=(BossTarget(game_id=6000, start_ms=200_000, end_ms=300_000),),
)
SECOND_UNFOUND = SECOND.model_copy(update={"targets": (), "withheld": Withheld.NO_BOSS})


def on_two_bosses(
    first: float,
    second: float,
    *,
    windows: tuple[BossWindow, ...] = (FIRST, SECOND),
    second_encounter: int = 2002,
) -> KeyDebuffs:
    covered = []
    if first > 0:
        covered.append((2001, DOT, int(100_000 * first)))
    if second > 0:
        covered.append((second_encounter, DOT, int(100_000 * second)))
    return KeyDebuffs(
        bosses=BossDebuffs(
            windows=windows,
            covered=tuple(covered),
            names=((DOT, DOT_NAME),) if covered else (),
            reached=((DOT, len(covered)),) if covered else (),
        )
    )


def test_a_row_carries_the_overall_verdict_and_one_cell_per_boss() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

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
    kill = FIRST.model_copy(
        update={
            "start_ms": 200_000,
            "end_ms": 300_000,
            "targets": (BossTarget(game_id=5000, start_ms=200_000, end_ms=300_000),),
        }
    )
    sample = a_sample_of(
        *(
            on_two_bosses(0.9, 0.9, windows=(FIRST, kill), second_encounter=2001)
            for _ in range(3)
        )
    )

    table = debuff_table(
        on_two_bosses(0.5, 0.9, windows=(FIRST, kill), second_encounter=2001), sample
    )

    assert table.bosses == ("First Boss",)
    assert table.seconds == 200.0
    [row] = table.rows
    [cell] = row.cells
    assert cell.encounter_id == 2001
    assert cell.ours == pytest.approx(0.7)
    assert cell.their_median == pytest.approx(0.9)


def test_our_unfound_boss_cell_is_withheld_with_its_reason() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.0, windows=(FIRST, SECOND_UNFOUND)), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", withheld=Withheld.NO_BOSS
    )


def test_a_boss_no_reference_reached_shows_ours_and_says_so() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.0, windows=(FIRST,)) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

    assert table.rows[0].cells[1] == BossCell(
        encounter_id=2002, boss="Second Boss", ours=0.9, withheld=Withheld.NOT_REACHED
    )


def test_a_boss_too_few_references_applied_it_on_shows_ours_and_says_so() -> None:
    sample = a_sample_of(
        on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.9), on_two_bosses(0.9, 0.0)
    )

    table = debuff_table(on_two_bosses(0.5, 0.9), sample)

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
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert debuff_table(on_two_bosses(0.5, 0.9), two).rows == ()
    assert debuff_table(None, three).rows == ()


def test_the_table_carries_our_count_of_deathless_council_bosses() -> None:
    window = FIRST.model_copy(update={"deathless": 1})
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(on_two_bosses(0.5, 0.9, windows=(window, SECOND)), sample)

    assert table.deathless == 1


def test_below_the_floor_the_empty_table_still_carries_our_deathless_count() -> None:
    window = FIRST.model_copy(update={"deathless": 2})
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )

    table = debuff_table(on_two_bosses(0.5, 0.9, windows=(window, SECOND)), two)

    assert table.rows == ()
    assert table.deathless == 2


def a_tallied_run() -> KeyDebuffs:
    return on_its_bosses(
        on_two_bosses(0.5, 0.9), tally=PairingTally(orphan_removes=2, closed_at_end=1)
    )


def test_our_own_pairing_tally_rides_on_the_table() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    assert debuff_table(a_tallied_run(), sample).tally == PairingTally(
        orphan_removes=2, closed_at_end=1
    )


def test_below_the_floor_the_empty_table_still_carries_our_own_tally_and_seconds() -> None:
    two = ParseSample(
        members=(
            a_member("Bríala", on_two_bosses(0.9, 0.9)),
            a_member("Кириллица", on_two_bosses(0.9, 0.9)),
        )
    )

    table = debuff_table(a_tallied_run(), two)

    assert table.rows == ()
    assert table.seconds == 200.0
    assert table.tally == PairingTally(orphan_removes=2, closed_at_end=1)


def test_with_no_measured_enemy_the_empty_table_still_carries_our_own_tally() -> None:
    unfound = KeyDebuffs(
        bosses=BossDebuffs(
            windows=(
                BossWindow(
                    encounter_id=2001,
                    name="The Fixture Hall",
                    start_ms=0,
                    end_ms=60_000,
                    withheld=Withheld.NO_BOSS,
                ),
            ),
            tally=PairingTally(orphan_removes=3),
        )
    )
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(unfound, three)

    assert table.rows == ()
    assert table.seconds == 0.0
    assert table.tally == PairingTally(orphan_removes=3)


def test_a_clean_log_records_a_zero_tally_not_an_absent_one() -> None:
    two = ParseSample(members=(a_member("Bríala", on_two_bosses(0.9, 0.9)),))

    table = debuff_table(on_two_bosses(0.5, 0.9), two)

    assert table.tally == PairingTally()
    assert table.tally is not None


def test_when_our_stream_could_not_be_read_the_table_records_no_tally() -> None:
    three = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))

    table = debuff_table(None, three)

    assert table.tally is None
    assert table.seconds == 0.0


TEAMMATE, SECOND_TEAMMATE = 702, 703


def marked_shared(debuffs: KeyDebuffs, ability_id: int, *owners: int) -> KeyDebuffs:
    return on_its_bosses(debuffs, shared_with=((ability_id, owners),))


def test_a_shared_debuff_far_below_the_sample_is_not_a_gap() -> None:
    ours = marked_shared(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_below_the_floor_a_shared_debuff_is_not_a_gap_either() -> None:
    ours = marked_shared(on_the_boss((DOT, DOT_NAME, 0.3)), DOT, TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9)) == []


def test_a_shared_debuff_we_never_applied_is_not_named_unjudged() -> None:
    ours = marked_shared(on_the_boss(), DOT, TEAMMATE, SECOND_TEAMMATE)

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


OTHER_DOT, OTHER_DOT_NAME = 55095, "Frost Fever"


def test_only_the_shared_debuff_is_set_aside() -> None:
    both = ((DOT, DOT_NAME, 0.9), (OTHER_DOT, OTHER_DOT_NAME, 0.9))
    sample = ParseSample(
        members=tuple(a_member(name, on_the_boss(*both)) for name in REFERENCE_NAMES)
    )
    ours = marked_shared(
        on_the_boss((DOT, DOT_NAME, 0.3), (OTHER_DOT, OTHER_DOT_NAME, 0.3)), DOT, TEAMMATE
    )

    findings = compare_debuffs_sample(ours, OUR_NAME, sample)

    assert [(finding.id, finding.ability_id) for finding in findings] == [
        ("compare.uptime.debuff.0", OTHER_DOT)
    ]


def test_a_teammate_taking_the_debuff_over_from_us_leaves_no_gap() -> None:
    # Read off a log: ours 10s of the 60s pull, the teammate's the other 50s,
    # never at once. The sample's 90% against our 17% would be a gap.
    ours = key_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 20_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    assert compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9)) == []


def test_a_teammates_copy_beside_ours_leaves_the_gap_standing() -> None:
    # The same figures, but the teammate's copy sat on the boss beside ours, so
    # theirs took nothing away from ours: the gap is ours.
    ours = key_debuffs(
        a_log(*held(PLAYER, 10_000, 20_000), *held(OTHER, 10_000, 70_000)),
        (BOSS_PULL,),
        PLAYER,
        RUN_PLAYERS,
    )

    findings = compare_debuffs_sample(ours, OUR_NAME, a_sample(0.9, 0.9, 0.9))

    assert [finding.id for finding in findings] == ["compare.uptime.debuff.0"]


def test_a_shared_row_keeps_its_figures_and_names_who_it_was_shared_with() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = marked_shared(on_two_bosses(0.5, 0.9), DOT, TEAMMATE, SECOND_TEAMMATE)

    [row] = debuff_table(ours, sample).rows

    assert row.shared_with == (TEAMMATE, SECOND_TEAMMATE)
    assert row.uptime.ours == pytest.approx(0.7)
    assert row.uptime.verdict is Verdict.BELOW


def test_a_row_whose_debuff_is_not_the_shared_one_names_nobody() -> None:
    sample = a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3)))
    ours = marked_shared(on_two_bosses(0.5, 0.9), OTHER_DOT, TEAMMATE)

    [row] = debuff_table(ours, sample).rows

    assert row.shared_with == ()


def test_the_players_measures_carry_the_debuff_table() -> None:
    subject = ComparisonSubject(
        player=a_player(),
        slug="stonewake-0",
        display_name=OUR_NAME,
        parse=a_sample_of(*(on_two_bosses(0.9, 0.9) for _ in range(3))),
        our_debuffs=on_two_bosses(0.5, 0.9),
    )

    measures = comparison_measures(LoadedRun(run=a_run(BOSS)), [subject])

    assert [row.uptime.name for row in measures["stonewake-0"].debuffs.rows] == [DOT_NAME]

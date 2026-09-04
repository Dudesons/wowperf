# ABOUTME: Behaviour tests for the individual comparison: which spells and which build.
# ABOUTME: Everything here is restricted to boss pulls, where the encounter is the same fight.

from wowperf.domain.comparison.spells import (
    MIN_CASTS_TO_COMPARE,
    boss_casts,
    boss_seconds,
    compare_spells,
    compare_talents,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import LoadedRun, Player, Pull, Run

OURS = Player(actor_id=693, name="Uglymage", class_name="Mage", spec="Arcane", item_level=318)
THEIRS = Player(
    actor_id=11,
    name="Críms",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)


def boss_pull(index: int, seconds: float) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk",
        encounter_id=2607,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=(),
    )


def trash_pull(index: int, seconds: float) -> Pull:
    pull = boss_pull(index, seconds)
    return pull.model_copy(update={"encounter_id": 0, "name": "Pack"})


def a_loaded(player: Player, pulls: tuple[Pull, ...], casts: tuple[CastEvent, ...]) -> LoadedRun:
    run = Run(
        report_code="abc123",
        fight_id=36,
        dungeon_name="Den of Nalorakk",
        encounter_id=12825,
        keystone_level=16,
        affix_ids=(9, 10, 147),
        keystone_time_ms=1_909_000,
        keystone_bonus=1,
        count_reached=744,
        count_required=729,
        npc_counts=(),
        players=(player,),
        pulls=pulls,
    )
    return LoadedRun(run=run, casts=casts)


def cast(actor_id: int, ability_id: int, name: str, at_ms: int, pull: int | None) -> CastEvent:
    return CastEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        timestamp_ms=at_ms,
        pull_index=pull,
    )


def test_boss_seconds_counts_only_boss_pulls() -> None:
    run = a_loaded(OURS, (boss_pull(0, 120.0), trash_pull(1, 60.0), boss_pull(2, 60.0)), ()).run

    assert boss_seconds(run) == 180.0


def test_boss_casts_ignore_trash_and_other_players() -> None:
    pulls = (boss_pull(0, 120.0), trash_pull(1, 60.0))
    casts = (
        cast(693, 30451, "Arcane Blast", 1_000, 0),
        cast(693, 30451, "Arcane Blast", 2_000, 0),
        cast(693, 30451, "Arcane Blast", 3_000, 1),
        cast(693, 30451, "Arcane Blast", 4_000, None),
        cast(7, 30451, "Arcane Blast", 5_000, 0),
    )
    run = a_loaded(OURS, pulls, casts).run

    counted = boss_casts(run, casts, actor_id=693)

    assert counted == {30451: ("Arcane Blast", 2)}


def test_an_ability_they_cast_and_we_never_did_is_reported() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 120.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 120.0),),
        (
            cast(11, 30451, "Arcane Blast", 1_000, 0),
            cast(11, 153626, "Arcane Orb", 2_000, 0),
            cast(11, 153626, "Arcane Orb", 3_000, 0),
        ),
    )

    findings = compare_spells(ours, OURS, theirs, "Críms")
    missing = [f for f in findings if f.id.startswith("compare.spells.missing.")]

    assert len(missing) == 1
    assert "Arcane Orb" in missing[0].title
    assert missing[0].confidence is Confidence.MEASURED
    assert missing[0].seconds_lost is None


def test_an_ability_we_cast_only_on_trash_still_counts_as_cast() -> None:
    ours = a_loaded(
        OURS,
        (boss_pull(0, 120.0), trash_pull(1, 60.0)),
        (cast(693, 153626, "Arcane Orb", 200_000, 1),),
    )
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 120.0),),
        tuple(cast(11, 153626, "Arcane Orb", n * 1_000, 0) for n in range(4)),
    )

    missing = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.missing.")
    ]

    assert missing == []


def test_a_rate_gap_on_a_shared_ability_is_derived() -> None:
    ours = a_loaded(
        OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),)
    )
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 30451, "Arcane Blast", n * 1_000, 0) for n in range(6)),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert len(rates) == 1
    assert rates[0].confidence is Confidence.DERIVED
    assert "Arcane Blast" in rates[0].title


def test_a_reference_cast_too_few_times_is_not_a_rate_finding() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(
            cast(11, 30451, "Arcane Blast", n * 1_000, 0)
            for n in range(MIN_CASTS_TO_COMPARE - 1)
        ),
    )

    rates = [
        f for f in compare_spells(ours, OURS, theirs, "Críms")
        if f.id.startswith("compare.spells.rate.")
    ]

    assert rates == []


def test_a_reference_with_no_boss_pulls_says_so_instead_of_dividing_by_zero() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(THEIRS, (trash_pull(0, 60.0),), ())

    findings = compare_spells(ours, OURS, theirs, "Críms")

    assert any(f.id == "compare.spells.unavailable" for f in findings)


def test_a_different_build_is_reported_with_their_string() -> None:
    finding = compare_talents(OURS.model_copy(update={"talent_import_string": "C4DAAAAA"}),
                              THEIRS)[0]

    assert finding.id == "compare.talents"
    assert finding.confidence is Confidence.MEASURED
    assert any("CoPAAAAA" in line for line in finding.evidence)


def test_an_identical_build_reports_that_it_matches() -> None:
    same = OURS.model_copy(update={"talent_import_string": "CoPAAAAA"})

    finding = compare_talents(same, THEIRS)[0]

    assert "matches" in finding.title.lower()


def test_a_missing_build_says_the_comparison_could_not_be_made() -> None:
    finding = compare_talents(OURS, THEIRS)[0]

    assert "not" in finding.detail.lower()
    assert finding.seconds_lost is None


def test_every_finding_id_is_unique() -> None:
    ours = a_loaded(OURS, (boss_pull(0, 60.0),), (cast(693, 30451, "Arcane Blast", 1_000, 0),))
    theirs = a_loaded(
        THEIRS,
        (boss_pull(0, 60.0),),
        tuple(cast(11, 100 + n, f"Spell {n}", n * 1_000, 0) for n in range(8) for _ in range(4)),
    )

    ids = [f.id for f in compare_spells(ours, OURS, theirs, "Críms")]

    assert len(ids) == len(set(ids))

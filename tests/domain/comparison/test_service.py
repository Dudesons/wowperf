# ABOUTME: Behaviour tests for running every comparison over one run and ranking the result.
# ABOUTME: Guards the two things only the service can get wrong: a missing reference, and a name.

from wowperf.domain.comparison.reference import (
    Comparability,
    ParseReference,
    ParseRow,
    SpeedReference,
    SpeedRow,
)
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run

OURS = Player(
    actor_id=693,
    name="Uglymage",
    class_name="Mage",
    spec="Arcane",
    item_level=318,
    talent_import_string="C4DAAAAA",
)
THEIRS = Player(
    actor_id=11,
    name="Críms",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)


def a_pull(index: int, game_ids: tuple[int, ...], boss: bool = False) -> Pull:
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Nalorakk" if boss else "Pack",
        encounter_id=2607 if boss else 0,
        start_ms=index * 200_000,
        end_ms=index * 200_000 + 60_000,
        killed=True,
        x=index,
        y=index,
        enemies=tuple(EnemyNpc(actor_id=100 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def a_loaded(players: tuple[Player, ...], pulls: tuple[Pull, ...], level: int = 16) -> LoadedRun:
    return LoadedRun(
        run=Run(
            report_code="abc123",
            fight_id=36,
            dungeon_name="Den of Nalorakk",
            encounter_id=12825,
            keystone_level=level,
            affix_ids=(9, 10, 147),
            keystone_time_ms=1_909_000,
            keystone_bonus=1,
            count_reached=744,
            count_required=729,
            npc_counts=((2, 12),),
            players=players,
            pulls=pulls,
            owner_name="uglymage",
        )
    )


def our_run() -> LoadedRun:
    return a_loaded((OURS,), (a_pull(0, (1,)), a_pull(1, (2,)), a_pull(2, (9,), boss=True)))


def a_speed_reference(level: int = 16) -> SpeedReference:
    return SpeedReference(
        row=SpeedRow(
            report_code="71cv4MRdNCp8ZFjG",
            fight_id=28,
            keystone_level=level,
            duration_ms=1_379_452,
            deaths=0,
            medal="silver",
        ),
        loaded=a_loaded((OURS,), (a_pull(0, (1,)), a_pull(1, (9,), boss=True)), level=level),
    )


def a_parse_reference() -> ParseReference:
    return ParseReference(
        row=ParseRow(
            report_code="37FzMg9pVPH6fnJT",
            fight_id=16,
            keystone_level=16,
            duration_ms=1_399_143,
            character_name="Críms",
            class_name="Mage",
            spec="Arcane",
        ),
        loaded=a_loaded((THEIRS,), (a_pull(0, (9,), boss=True),)),
    )


def test_a_player_is_found_whatever_the_case() -> None:
    assert find_player(our_run().run, "uglymage") is OURS
    assert find_player(our_run().run, "UGLYMAGE") is OURS
    assert find_player(our_run().run, "Nobody") is None


def test_every_comparison_contributes() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())
    prefixes = {".".join(finding.id.split(".")[:2]) for finding in findings}

    assert {"compare.route", "compare.downtime", "compare.deaths", "compare.talents"} <= prefixes


def test_findings_come_back_ranked() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]

    assert timed == sorted(timed, reverse=True)


def test_every_finding_id_is_unique() -> None:
    ids = [f.id for f in compare(our_run(), OURS, a_speed_reference(), a_parse_reference())]

    assert len(ids) == len(set(ids))


def test_every_finding_carries_a_badge() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), a_parse_reference())

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_no_speed_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, None, a_parse_reference())

    assert any(f.id == "compare.speed.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.route.") for f in findings)


def test_no_parse_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(), None)

    assert any(f.id == "compare.parse.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.spells.") for f in findings)


def test_neither_reference_still_produces_a_usable_list() -> None:
    findings = compare(our_run(), OURS, None, None)

    assert len(findings) == 2
    assert all(finding.seconds_lost is None for finding in findings)


def test_a_reference_at_another_level_withholds_the_duration() -> None:
    findings = compare(our_run(), OURS, a_speed_reference(level=17), None)
    duration = next(f for f in findings if f.id == "compare.duration")

    assert duration.seconds_lost is None
    assert Comparability(our_level=16, their_level=17).withheld_because() == duration.detail

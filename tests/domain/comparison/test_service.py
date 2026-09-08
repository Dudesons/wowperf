# ABOUTME: Behaviour tests for running every comparison over one run and ranking the result.
# ABOUTME: Guards the two things only the service can get wrong: a missing reference, and a name.

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.reference import (
    Comparability,
    ParseReference,
    ParseRow,
    SpeedReference,
    SpeedRow,
)
from wowperf.domain.comparison.sample import ParseMember, ParseSample, SpeedMember, SpeedSample
from wowperf.domain.comparison.service import compare, find_player
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run

OURS = Player(
    actor_id=693,
    name="Emberkin",
    class_name="Mage",
    spec="Arcane",
    item_level=318,
    talent_import_string="C4DAAAAA",
)
THEIRS = Player(
    actor_id=11,
    name="Bríala",
    class_name="Mage",
    spec="Arcane",
    item_level=330,
    talent_import_string="CoPAAAAA",
)
# The speed leaderboard's own roster: a different composition and a wide enough
# item-level gap from OURS that declare_confounds has something to say about it.
SPEED_TEAM_MEMBER = Player(
    actor_id=44,
    name="Fastclear",
    class_name="Rogue",
    spec="Outlaw",
    item_level=333,
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


def a_loaded(
    players: tuple[Player, ...],
    pulls: tuple[Pull, ...],
    level: int = 16,
    casts: tuple[CastEvent, ...] = (),
) -> LoadedRun:
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
            owner_name="emberkin",
        ),
        casts=casts,
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
        loaded=a_loaded(
            (SPEED_TEAM_MEMBER,),
            (a_pull(0, (1,)), a_pull(1, (9,), boss=True)),
            level=level,
        ),
    )


def a_speed_member(level: int = 16) -> SpeedMember:
    """`a_speed_reference` wrapped as the member a one-member `SpeedSample` carries."""
    reference = a_speed_reference(level=level)
    theirs_run = reference.loaded.run
    return SpeedMember(
        row=reference.row,
        run=theirs_run,
        comparability=Comparability(our_level=16, their_level=level),
        alignment=align_pulls(our_run().run, theirs_run),
        deaths=reference.loaded.deaths,
        enemy_cast_rows=reference.loaded.enemy_cast_rows,
        interrupts=reference.loaded.interrupts,
    )


def a_speed_sample(level: int = 16) -> SpeedSample:
    return SpeedSample(members=(a_speed_member(level=level),))


def a_parse_reference(auras: PlayerAuras | None = None) -> ParseReference:
    return ParseReference(
        row=ParseRow(
            report_code="37FzMg9pVPH6fnJT",
            fight_id=16,
            keystone_level=16,
            duration_ms=1_399_143,
            character_name="Bríala",
            class_name="Mage",
            spec="Arcane",
        ),
        loaded=a_loaded(
            (THEIRS,),
            (a_pull(0, (9,), boss=True),),
            casts=(
                # Cast on a boss pull, by an ability id OURS never casts anywhere in
                # our_run() — the set-difference branch of compare_spells needs no
                # minimum count, unlike the rate-gap branch.
                CastEvent(
                    actor_id=THEIRS.actor_id,
                    ability_id=190319,
                    ability_name="Combustion",
                    timestamp_ms=10_000,
                    pull_index=0,
                ),
            ),
        ),
        auras=auras,
    )


def a_parse_member(auras: PlayerAuras | None = None) -> ParseMember:
    """`a_parse_reference` wrapped as the member a one-member `ParseSample` carries."""
    reference = a_parse_reference(auras=auras)
    return ParseMember(
        row=reference.row,
        run=reference.loaded.run,
        comparability=Comparability(our_level=16, their_level=reference.row.keystone_level),
        casts=reference.loaded.casts,
        auras=reference.auras,
    )


def a_parse_sample(auras: PlayerAuras | None = None) -> ParseSample:
    return ParseSample(members=(a_parse_member(auras=auras),))


# OURS's boss pull in our_run() runs 400_000-460_000ms; the parse reference's runs
# 0-60_000ms. Both are 60s, so a 90-point uptime gap on the same ability clears
# UPTIME_GAP_FRACTION regardless of which side's window backs the fraction.
OUR_AURAS = PlayerAuras(
    actor_id=OURS.actor_id,
    on_self=(
        Aura(
            ability_id=12042,
            name="Arcane Power",
            total_uptime_ms=3_000,
            uses=1,
            bands=(AuraBand(start_ms=400_000, end_ms=403_000),),
        ),
    ),
)
THEIR_AURAS = PlayerAuras(
    actor_id=THEIRS.actor_id,
    on_self=(
        Aura(
            ability_id=12042,
            name="Arcane Power",
            total_uptime_ms=57_000,
            uses=1,
            bands=(AuraBand(start_ms=0, end_ms=57_000),),
        ),
    ),
)


def a_comparable_pair_with_auras() -> tuple[LoadedRun, Player, SpeedSample, ParseSample]:
    """The usual comparable pair, with aura data riding along on the parse side.

    Extends `a_parse_reference` rather than a parallel fixture, so the boss pull
    that grounds the aura windows can't drift out of sync with the plain one.
    """
    return our_run(), OURS, a_speed_sample(), a_parse_sample(auras=THEIR_AURAS)


def test_a_player_is_found_whatever_the_case() -> None:
    assert find_player(our_run().run, "emberkin") is OURS
    assert find_player(our_run().run, "EMBERKIN") is OURS
    assert find_player(our_run().run, "Nobody") is None


def test_every_comparison_contributes() -> None:
    findings = compare(our_run(), OURS, a_speed_sample(), a_parse_sample())
    prefixes = {".".join(finding.id.split(".")[:2]) for finding in findings}

    assert {
        "compare.route",
        "compare.downtime",
        "compare.deaths",
        "compare.talents",
        "compare.confound",
        "compare.spells",
    } <= prefixes


def test_findings_come_back_ranked() -> None:
    findings = compare(our_run(), OURS, a_speed_sample(), a_parse_sample())
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]

    assert timed == sorted(timed, reverse=True)


def test_every_finding_id_is_unique() -> None:
    ids = [f.id for f in compare(our_run(), OURS, a_speed_sample(), a_parse_sample())]

    assert len(ids) == len(set(ids))


def test_every_finding_carries_a_badge() -> None:
    findings = compare(our_run(), OURS, a_speed_sample(), a_parse_sample())

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_no_speed_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, None, a_parse_sample())

    assert any(f.id == "compare.speed.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.route.") for f in findings)


def test_no_parse_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), OURS, a_speed_sample(), None)

    assert any(f.id == "compare.parse.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.spells.") for f in findings)


def test_neither_reference_still_produces_a_usable_list() -> None:
    findings = compare(our_run(), OURS, None, None)

    assert len(findings) == 2
    assert all(finding.seconds_lost is None for finding in findings)


def test_a_reference_at_another_level_withholds_the_duration() -> None:
    findings = compare(our_run(), OURS, a_speed_sample(level=17), None)
    duration = next(f for f in findings if f.id == "compare.duration")

    assert duration.seconds_lost is None
    assert Comparability(our_level=16, their_level=17).withheld_because() == duration.detail


def test_uptime_findings_appear_when_both_sides_carry_auras() -> None:
    ours, our_player, speed, parse = a_comparable_pair_with_auras()

    ids = {f.id.rsplit(".", 1)[0] for f in compare(ours, our_player, speed, parse,
                                                   our_auras=OUR_AURAS)}

    assert "compare.uptime.self" in ids


def test_a_comparison_without_auras_says_uptime_was_not_compared() -> None:
    ours, our_player, speed, parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, our_player, speed, parse)]

    assert "compare.uptime.unavailable" in ids


def test_no_parse_reference_means_no_uptime_findings_at_all() -> None:
    ours, our_player, speed, _parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, our_player, speed, None, our_auras=OUR_AURAS)]

    assert [i for i in ids if i.startswith("compare.uptime.")] == []
    assert "compare.parse.unavailable" in ids


def test_an_empty_speed_sample_reports_the_speed_comparison_unavailable() -> None:
    findings = compare(
        ours=our_run(), our_player=OURS, speed=SpeedSample(), parse=None, our_auras=None
    )

    assert any(finding.id == "compare.speed.unavailable" for finding in findings)


def test_a_one_member_sample_compares_against_that_member() -> None:
    findings = compare(
        ours=our_run(),
        our_player=OURS,
        speed=SpeedSample(members=(a_speed_member(),)),
        parse=None,
        our_auras=None,
    )

    assert any(finding.id == "compare.route.summary" for finding in findings)
    assert not any(finding.id == "compare.speed.unavailable" for finding in findings)

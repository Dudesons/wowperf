# ABOUTME: Behaviour tests for running every comparison over one run and ranking the result.
# ABOUTME: Guards a missing reference, a name, which axis addresses a player, and unique ids.

import pytest
from pydantic import ValidationError

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.reference import Comparability, ParseRow, SpeedRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample, SpeedMember, SpeedSample
from wowperf.domain.comparison.service import ComparisonSubject, compare, find_player
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
# A second subject, so a comparison over more than one player has two slugs to
# keep apart.
SECOND = Player(
    actor_id=694,
    name="Stonewake",
    class_name="DeathKnight",
    spec="Blood",
    item_level=320,
    talent_import_string="C4DAAAAB",
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


def a_speed_member(level: int = 16) -> SpeedMember:
    """The member a one-member `SpeedSample` carries: one fast run at `level`."""
    theirs = a_loaded(
        (SPEED_TEAM_MEMBER,),
        (a_pull(0, (1,)), a_pull(1, (9,), boss=True)),
        level=level,
    )
    return SpeedMember(
        row=SpeedRow(
            report_code="71cv4MRdNCp8ZFjG",
            fight_id=28,
            keystone_level=level,
            duration_ms=1_379_452,
            deaths=0,
            medal="silver",
        ),
        run=theirs.run,
        comparability=Comparability(our_level=16, their_level=level),
        alignment=align_pulls(our_run().run, theirs.run),
        deaths=theirs.deaths,
        enemy_cast_rows=theirs.enemy_cast_rows,
        interrupts=theirs.interrupts,
    )


def a_speed_sample(level: int = 16) -> SpeedSample:
    return SpeedSample(members=(a_speed_member(level=level),))


def a_parse_member(auras: PlayerAuras | None = None) -> ParseMember:
    """The member a one-member `ParseSample` carries: one top parse of our own spec."""
    theirs = a_loaded(
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
    )
    return ParseMember(
        row=ParseRow(
            report_code="37FzMg9pVPH6fnJT",
            fight_id=16,
            keystone_level=16,
            duration_ms=1_399_143,
            character_name="Bríala",
            class_name="Mage",
            spec="Arcane",
        ),
        run=theirs.run,
        casts=theirs.casts,
        auras=auras,
    )


def a_parse_sample(auras: PlayerAuras | None = None) -> ParseSample:
    return ParseSample(members=(a_parse_member(auras=auras),))


OUR_SLUG = "emberkin-0"
"""OURS's fragment id: what `slugs_by_actor` mints for the first roster entry."""


def only_ours(
    parse: ParseSample | None, our_auras: PlayerAuras | None = None
) -> tuple[ComparisonSubject, ...]:
    """The subjects tuple for a comparison that looks at OURS and nobody else."""
    return (
        ComparisonSubject(
            player=OURS,
            slug=OUR_SLUG,
            display_name=OURS.name,
            parse=parse,
            our_auras=our_auras,
        ),
    )


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


def a_comparable_pair_with_auras() -> tuple[LoadedRun, SpeedSample, ParseSample]:
    """The usual comparable pair, with aura data riding along on the parse side.

    Extends `a_parse_member` rather than a parallel fixture, so the boss pull
    that grounds the aura windows can't drift out of sync with the plain one.
    """
    return our_run(), a_speed_sample(), a_parse_sample(auras=THEIR_AURAS)


def test_a_player_is_found_whatever_the_case() -> None:
    assert find_player(our_run().run, "emberkin") is OURS
    assert find_player(our_run().run, "EMBERKIN") is OURS
    assert find_player(our_run().run, "Nobody") is None


def test_every_comparison_contributes() -> None:
    findings = compare(our_run(), a_speed_sample(), only_ours(a_parse_sample()))
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
    findings = compare(our_run(), a_speed_sample(), only_ours(a_parse_sample()))
    timed = [f.seconds_lost for f in findings if f.seconds_lost is not None]

    assert timed == sorted(timed, reverse=True)


def test_every_finding_id_is_unique() -> None:
    ids = [f.id for f in compare(our_run(), a_speed_sample(), only_ours(a_parse_sample()))]

    assert len(ids) == len(set(ids))


def test_every_finding_carries_a_badge() -> None:
    findings = compare(our_run(), a_speed_sample(), only_ours(a_parse_sample()))

    assert all(isinstance(finding.confidence, Confidence) for finding in findings)


def test_no_speed_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), None, only_ours(a_parse_sample()))

    assert any(f.id == "compare.speed.unavailable" for f in findings)
    assert not any(f.id.startswith("compare.route.") for f in findings)


def test_no_parse_reference_is_a_finding_not_a_crash() -> None:
    findings = compare(our_run(), a_speed_sample(), only_ours(None))

    assert any(f.id == f"compare.parse.unavailable.{OUR_SLUG}" for f in findings)
    assert not any(f.id.startswith("compare.spells.") for f in findings)


def test_neither_reference_still_produces_a_usable_list() -> None:
    findings = compare(our_run(), None, only_ours(None))

    assert len(findings) == 2
    assert all(finding.seconds_lost is None for finding in findings)


def test_a_reference_at_another_level_withholds_the_duration() -> None:
    findings = compare(our_run(), a_speed_sample(level=17), only_ours(None))
    duration = next(f for f in findings if f.id == "compare.duration")

    assert duration.seconds_lost is None
    assert Comparability(our_level=16, their_level=17).withheld_because() == duration.detail


def test_uptime_findings_appear_when_both_sides_carry_auras() -> None:
    ours, speed, parse = a_comparable_pair_with_auras()

    findings = compare(ours, speed, only_ours(parse, our_auras=OUR_AURAS))

    assert any(f.id.startswith("compare.uptime.self.") for f in findings)


def test_a_comparison_without_auras_says_uptime_was_not_compared() -> None:
    ours, speed, parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, speed, only_ours(parse))]

    assert f"compare.uptime.unavailable.{OUR_SLUG}" in ids


def test_no_parse_reference_means_no_uptime_findings_at_all() -> None:
    ours, speed, _parse = a_comparable_pair_with_auras()

    ids = [f.id for f in compare(ours, speed, only_ours(None, our_auras=OUR_AURAS))]

    assert [i for i in ids if i.startswith("compare.uptime.")] == []
    assert f"compare.parse.unavailable.{OUR_SLUG}" in ids


def test_an_empty_speed_sample_reports_the_speed_comparison_unavailable() -> None:
    findings = compare(ours=our_run(), speed=SpeedSample(), subjects=only_ours(None))

    assert any(finding.id == "compare.speed.unavailable" for finding in findings)


def test_a_one_member_sample_compares_against_that_member() -> None:
    findings = compare(
        ours=our_run(),
        speed=SpeedSample(members=(a_speed_member(),)),
        subjects=only_ours(None),
    )

    assert any(finding.id == "compare.route.summary" for finding in findings)
    assert not any(finding.id == "compare.speed.unavailable" for finding in findings)


def test_a_subject_cannot_be_built_without_a_slug() -> None:
    # An empty slug mints `compare.talents.` -- a family prefix with a trailing
    # dot -- and stamps a `player_slug` of "" that no consumer can tell from a
    # run-level finding's. Both corruptions are silent, so the slug is refused
    # at the door rather than checked by everyone who reads one.
    with pytest.raises(ValidationError):
        ComparisonSubject(player=OURS, slug="", display_name=OURS.name, parse=None)


def test_a_parse_finding_carries_the_player_it_is_about() -> None:
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(ComparisonSubject(
            player=OURS,
            slug="emberkin-0",
            display_name=OURS.name,
            parse=a_parse_sample(),
        ),),
    )
    talents = next(f for f in findings if f.id.startswith("compare.talents"))

    assert talents.id == "compare.talents.emberkin-0"
    assert talents.player_slug == "emberkin-0"


def test_a_speed_finding_names_no_player() -> None:
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(ComparisonSubject(
            player=OURS,
            slug="emberkin-0",
            display_name=OURS.name,
            parse=a_parse_sample(),
        ),),
    )
    speed = next(f for f in findings if f.id == "compare.speed.unavailable")

    assert speed.player_slug == ""


PARSE_FAMILIES = (
    "compare.spells.",
    "compare.talents",
    "compare.uptime.",
    "compare.parse.unavailable",
)
"""The families drawn per player. Everything else `compare` emits is about the run.

The route, the tempo, the downtime, the deaths, the interrupts, the duration
and the confounds are measured once against one fast run, whoever is being
looked at, so none of them may carry a player.
"""


def test_only_the_parse_families_address_a_player() -> None:
    # The partition, not one family of it: a refactor that drew the tempo
    # inside the per-player half would suffix four more ids and stamp four
    # more slugs, and an assertion naming `compare.speed.unavailable` alone
    # would stay green through it.
    findings = compare(our_run(), a_speed_sample(), only_ours(a_parse_sample()))
    about_a_player = [f for f in findings if f.id.startswith(PARSE_FAMILIES)]
    about_the_run = [f for f in findings if not f.id.startswith(PARSE_FAMILIES)]

    # Neither half may be empty, or the halves below prove nothing.
    assert about_a_player
    assert about_the_run
    assert all(f.player_slug == OUR_SLUG for f in about_a_player)
    assert all(f.id.endswith(f".{OUR_SLUG}") for f in about_a_player)
    assert all(f.player_slug == "" for f in about_the_run)
    assert not any(f.id.endswith(OUR_SLUG) for f in about_the_run)


def test_two_players_produce_no_duplicate_finding_id() -> None:
    # The assertion that did not exist before this work. Colliding ids overwrite
    # entries in the report's title lookup and emit duplicate HTML element ids,
    # neither of which any other test can see.
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(
            ComparisonSubject(
            player=OURS,
            slug="emberkin-0",
            display_name=OURS.name,
            parse=a_parse_sample(),
        ),
            ComparisonSubject(
                player=SECOND,
                slug="stonewake-1",
                display_name=SECOND.name,
                parse=a_parse_sample(),
            ),
        ),
    )
    ids = [finding.id for finding in findings]

    assert len(ids) == len(set(ids))


def test_two_players_produce_no_duplicate_finding_title() -> None:
    # The companion to the id test above, and the harder half: an id is minted
    # once, in `_for_player`, while a title is written by whichever module
    # emitted the finding. A family whose title names nobody reads identically
    # under two cards, and in the findings file -- which is what the narrative
    # is written from -- there is then no way to say whose build differed.
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(
            ComparisonSubject(
                player=OURS, slug="emberkin-0", display_name="Emberkin", parse=a_parse_sample()
            ),
            ComparisonSubject(
                player=SECOND,
                slug="stonewake-1",
                display_name="Stonewake",
                parse=a_parse_sample(),
            ),
        ),
    )
    titles = [finding.title for finding in findings]

    assert len(titles) == len(set(titles))


def test_a_player_with_no_parse_sample_says_so_in_their_own_name() -> None:
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(ComparisonSubject(
            player=OURS, slug="emberkin-0", display_name=OURS.name, parse=None
        ),),
    )
    unavailable = next(f for f in findings if f.id == "compare.parse.unavailable.emberkin-0")

    assert OURS.name in unavailable.title


def test_a_player_with_no_specialisation_is_not_told_the_leaderboard_was_empty() -> None:
    """A log can record no specialisation for a player, and no leaderboard can
    then be asked for one. Saying the leaderboard returned nothing would state
    a fact about the API that was never established."""
    specless = OURS.model_copy(update={"spec": ""})
    findings = compare(
        ours=our_run(),
        speed=None,
        subjects=(ComparisonSubject(
            player=specless, slug="emberkin-0", display_name=OURS.name, parse=None
        ),),
    )
    unavailable = next(f for f in findings if f.id == "compare.parse.unavailable.emberkin-0")

    assert "no specialisation" in unavailable.detail
    assert "leaderboard returned nothing" not in unavailable.detail
    # The title names the player without a trailing gap where the spec would be.
    assert unavailable.title == f"No ranked parse was available for {OURS.name} (Mage)"

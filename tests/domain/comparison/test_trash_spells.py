# ABOUTME: Behaviour tests for the trash-pack half of the individual comparison.
# ABOUTME: Only packs two routes shared are compared, and only their own seconds count.

from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.comparison.trash_spells import (
    MIN_ALIGNED_TRASH_SECONDS,
    AlignedTrash,
    aligned_trash,
    compare_trash_spells_sample,
    is_comparable,
)
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, LoadedRun, Player, Pull, Run

OURS = Player(
    actor_id=693, name="Emberkin", class_name="DeathKnight", spec="Blood", item_level=318
)
THEIRS = Player(
    actor_id=11, name="Bríala", class_name="DeathKnight", spec="Blood", item_level=330
)


def a_pull(index: int, seconds: float, *game_ids: int, encounter_id: int = 0) -> Pull:
    """A pull holding one enemy actor per game id, so alignment can match on types."""
    return Pull(
        index=index,
        pull_id=index + 1,
        name="Pack" if encounter_id == 0 else "Boss",
        encounter_id=encounter_id,
        start_ms=index * 400_000,
        end_ms=index * 400_000 + int(seconds * 1000),
        killed=True,
        x=0,
        y=0,
        enemies=tuple(EnemyNpc(actor_id=1000 + n, game_id=g) for n, g in enumerate(game_ids)),
    )


def a_run(player: Player, *pulls: Pull) -> Run:
    return Run(
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


BLOOD_BOIL = 50842


def cast(actor_id: int, ability_id: int, name: str, at_ms: int, pull: int | None) -> CastEvent:
    return CastEvent(
        actor_id=actor_id,
        ability_id=ability_id,
        ability_name=name,
        timestamp_ms=at_ms,
        pull_index=pull,
    )


def a_loaded(player: Player, *pulls: Pull, casts: tuple[CastEvent, ...] = ()) -> LoadedRun:
    return LoadedRun(run=a_run(player, *pulls), casts=casts)


def a_trash_member(name: str, actor_id: int, blood_boils: int) -> ParseMember:
    """A reference who fought our pack for 60s and pressed Blood Boil that often."""
    player = Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=320
    )
    run = a_run(player, a_pull(0, 60.0, 100, 101))
    casts = tuple(
        cast(actor_id, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(blood_boils)
    )
    return ParseMember(
        row=ParseRow(
            report_code=f"REF{actor_id}",
            fight_id=1,
            keystone_level=16,
            duration_ms=1_909_000,
            character_name=name,
            class_name="DeathKnight",
            spec="Blood",
        ),
        run=run,
        casts=casts,
    )


# Four press Blood Boil 10 times over their 60s pack; the fifth never does.
TRASH_SAMPLE = ParseSample(
    members=(
        a_trash_member("Bríala", 11, 10),
        a_trash_member("Dawnseeker", 12, 10),
        a_trash_member("Emberfall", 13, 10),
        a_trash_member("Frostwhisper", 14, 10),
        a_trash_member("Glimmerose", 15, 0),
    )
)

# Our own run: the same pack, 60s, pressed 4 times - well past the 1.5x bar.
OURS_LOADED = a_loaded(
    OURS,
    a_pull(0, 60.0, 100, 101),
    casts=tuple(cast(693, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(4)),
)

OUR_NAME = "Emberkin (actor 693)"


def test_only_packs_both_routes_fought_are_counted() -> None:
    ours = a_run(OURS, a_pull(0, 60.0, 100, 101), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 60.0
    assert aligned.their_seconds == 30.0
    assert aligned.pack_count == 1


def test_one_chain_pull_of_ours_counts_its_seconds_once() -> None:
    """align_pulls sweeps back over their unclaimed pulls and can name the same
    pull of ours twice. Summing per match would count our stretch twice, inflate
    our denominator and depress our own rate - an error that makes the player
    look worse than they were."""
    ours = a_run(OURS, a_pull(0, 90.0, 100, 101, 200, 201))
    theirs = a_run(THEIRS, a_pull(0, 30.0, 100, 101), a_pull(1, 25.0, 200, 201))

    aligned = aligned_trash(ours, theirs)

    # Both of their packs matched our single stretch.
    assert aligned.their_pulls == frozenset({0, 1})
    assert aligned.their_seconds == 55.0
    # Ours is one pull and counts once, however many of theirs it covered.
    assert aligned.our_pulls == frozenset({0})
    assert aligned.our_seconds == 90.0
    assert aligned.pack_count == 1


def test_boss_pulls_are_not_aligned_trash() -> None:
    """Bosses match by encounter id and are the other comparison's subject. Counting
    them here would put the same seconds in two denominators."""
    ours = a_run(OURS, a_pull(0, 60.0, 100, encounter_id=2607), a_pull(1, 40.0, 200))
    theirs = a_run(THEIRS, a_pull(0, 55.0, 100, encounter_id=2607), a_pull(1, 35.0, 200))

    aligned = aligned_trash(ours, theirs)

    assert aligned.our_pulls == frozenset({1})
    assert aligned.our_seconds == 40.0


def test_a_denominator_below_the_floor_is_not_comparable() -> None:
    """A handful of seconds turns two casts into a wild rate. The floor is the only
    guard the rate rows have against a tiny denominator."""
    thin = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS - 0.1,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS * 10,
    )

    assert not is_comparable(thin)


def test_either_side_below_the_floor_disqualifies_the_pair() -> None:
    """A rate needs both denominators. A reference with almost no aligned trash is
    as useless as our own side having almost none."""
    theirs_thin = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS * 10,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS - 0.1,
    )

    assert not is_comparable(theirs_thin)


def test_both_sides_at_the_floor_are_comparable() -> None:
    at_floor = AlignedTrash(
        our_pulls=frozenset({0}),
        their_pulls=frozenset({0}),
        our_seconds=MIN_ALIGNED_TRASH_SECONDS,
        their_seconds=MIN_ALIGNED_TRASH_SECONDS,
    )

    assert is_comparable(at_floor)


def test_a_trash_rate_gap_states_its_pack_count_in_the_title() -> None:
    """Permissive alignment means thin rows appear. The denominator rides in the
    title so a row drawn from one pack cannot be quoted as though drawn from eight."""
    findings = compare_trash_spells_sample(OURS_LOADED, OURS, OUR_NAME, TRASH_SAMPLE)

    rate = next(f for f in findings if f.id == "compare.spells.trash.rate.0")
    assert "across 1 aligned pack" in rate.title
    assert "Blood Boil" in rate.title
    assert rate.confidence is Confidence.DERIVED
    assert rate.seconds_lost is None


def test_casts_on_a_boss_pull_do_not_inflate_our_trash_rate() -> None:
    """The two families must not price the same seconds twice.

    The ability is one the sample casts, and it is pressed hard on the boss and
    sparingly on the pack. Counting the boss presses would take our rate past
    the sample's and delete the row entirely, so the figure in the title is
    what pins the scoping - an ability the sample never casts would be kept out
    by the member count instead, and prove nothing about which pulls were read.
    """
    ours = a_loaded(
        OURS,
        a_pull(0, 60.0, 100, 101),
        a_pull(1, 60.0, 300, encounter_id=2607),
        casts=tuple(cast(693, BLOOD_BOIL, "Blood Boil", n * 1_000, 0) for n in range(4))
        + tuple(cast(693, BLOOD_BOIL, "Blood Boil", 100_000 + n * 1_000, 1) for n in range(20)),
    )

    findings = compare_trash_spells_sample(ours, OURS, OUR_NAME, TRASH_SAMPLE)

    rate = next(f for f in findings if f.id == "compare.spells.trash.rate.0")
    assert rate.title.endswith("casts it 4.0")
    assert "ours over 60s of aligned trash" in rate.evidence


def test_a_side_below_the_floor_contributes_no_rate() -> None:
    """A pair whose aligned trash is too thin is not argued from, and its absence
    must not be mistaken for anyone having cast nothing.

    The pack runs half the floor rather than a fraction of a second: under
    MIN_PACK_SECONDS it would never be a pack at all, alignment would drop it
    before the floor was consulted, and this test would pass with the floor
    deleted. Every other threshold here is deliberately cleared - five members,
    four of them casting - so the floor is the only guard left holding the row
    back.
    """
    half_the_floor = a_loaded(
        OURS,
        a_pull(0, MIN_ALIGNED_TRASH_SECONDS / 2, 100, 101),
        casts=(cast(693, BLOOD_BOIL, "Blood Boil", 100, 0),),
    )

    findings = compare_trash_spells_sample(half_the_floor, OURS, OUR_NAME, TRASH_SAMPLE)

    assert not any(f.id.startswith("compare.spells.trash.rate") for f in findings)

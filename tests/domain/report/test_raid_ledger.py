# ABOUTME: Every raid finding family lands on a tab somebody chose, or on a raider's card.
# ABOUTME: Holds the registry against the service so a new family cannot go silently unplaced.

from tests.domain.analysis.test_encounter_service import (
    ARCANE_BLAST,
    RAID,
    RAID_SLUGS,
    a_parse_subject,
    a_standing,
)
from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
)
from wowperf.domain.comparison.parse_axis import ParseSubject
from wowperf.domain.comparison.sample import ParseMember, ParseSample
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, EnemyCastRow
from wowperf.domain.findings import Finding
from wowperf.domain.model import Player
from wowperf.domain.report.raid_ledger import (
    RAID_COMPARISON_PREFIXES,
    RAID_PLACEMENTS,
    _raid_field_for,
)
from wowperf.domain.season import ConsumableCategory, Consumables, DefensiveAbility, Defensives

RAID_FAMILIES = (
    "deaths.total", "deaths.single.0", "deaths.chain.0", "deaths.repeat.emberkin",
    "defensives.ceiling.emberkin.0",
    "defensives.unused.emberkin", "consumables.never.emberkin",
    "consumables.unused.emberkin", "interrupts.summary", "interrupts.ability.0",
    "mechanics.ability.0", "mechanics.lethal.0", "players.damage.0",
    "compare.damage.total.emberkin-0", "compare.damage.targets.emberkin-0",
    "compare.rank.emberkin-0", "compare.parse.unavailable.emberkin-0",
    "compare.spells.missing.0.emberkin-0", "compare.spells.rate.0.emberkin-0",
    "compare.spells.above.0.emberkin-0", "compare.spells.level.emberkin-0",
    "compare.talents.emberkin-0", "compare.uptime.self.0.emberkin-0",
    "compare.uptime.unjudged.emberkin-0",
)
"""Every family `analyse_encounter` can emit from a kill without phases.

`mechanics.phase.*` and `wipe.cause` are absent because this fixture is a
kill and names no phases, not because their routing is unchecked: both are
pinned directly against `_raid_field_for` beside the tests that use this.

Enumerated rather than generated: a family this list forgets is a row that
falls silently through to `observations`, which is a tab a reader does not
look under for it. `test_the_family_list_matches_what_the_service_emits`
below holds the list against the service.
"""

_FAMILY_PREFIXES = (
    "deaths.total",
    "deaths.single.",
    "deaths.chain.",
    "deaths.repeat.",
    "defensives.ceiling.",
    "defensives.unused.",
    "consumables.never.",
    "consumables.unused.",
    "interrupts.summary",
    "interrupts.ability.",
    "mechanics.ability.",
    "mechanics.lethal.",
    "players.damage.",
    "compare.damage.total.",
    "compare.damage.targets.",
    "compare.rank.",
    "compare.parse.unavailable.",
    "compare.spells.missing.",
    "compare.spells.rate.",
    "compare.spells.above.",
    "compare.spells.level.",
    "compare.talents.",
    "compare.uptime.self.",
    "compare.uptime.unjudged.",
)
"""The fixed stem of every entry in `RAID_FAMILIES`, in the same order.

One prefix per family, standing for the id with its rank, slug or player name
stripped off -- the part that never changes between two runs. Sorted by
length before matching so a shorter stem never shadows a longer one that
starts the same way (none of these actually overlap, but `_family` does not
get to assume that stays true).
"""


def _family(finding_id: str) -> str:
    """Reduce a finding id to its placement-relevant prefix.

    Two ids belong to the same family when they differ only in a rank, a
    player slug or a player name -- exactly the parts `RAID_FAMILIES` above
    fills in with a placeholder. Matching the longest known stem first is what
    lets a real id (`deaths.repeat.Stonewake`) and its placeholder
    (`deaths.repeat.emberkin`) reduce to the same string despite naming
    different players.
    """
    for prefix in sorted(_FAMILY_PREFIXES, key=len, reverse=True):
        if finding_id.startswith(prefix):
            return prefix
    return finding_id


def test_every_raid_family_lands_somewhere_deliberate() -> None:
    """No raid family reaches the catch-all by accident.

    `build_observations` is a structural catch-all so a new family is never
    dropped, which is right -- but every family this slice already emits has a
    tab it belongs on, and falling through means nobody chose.
    """
    for finding_id in RAID_FAMILIES:
        placed = _raid_field_for(finding_id)
        on_a_card = any(
            finding_id.startswith(prefix) for prefix in RAID_COMPARISON_PREFIXES
        )
        assert placed is not None or on_a_card, finding_id


def test_the_mechanics_family_is_placed_at_all() -> None:
    """The defect this task exists to fix, named on its own.

    Plan 2 shipped `mechanics.ability.*` and the shared `PLACEMENTS` has no
    `mechanics.` prefix, so on a page built from the Mythic+ table every
    mechanics finding falls through to the observations catch-all.
    """
    assert _raid_field_for("mechanics.ability.0") == "mechanics_rows"


def test_the_throughput_families_reach_the_damage_tab() -> None:
    """Design section 6 groups 6.1, 6.2 and 6.7 together, and so does the page."""
    assert _raid_field_for("compare.damage.total.emberkin-0") == "damage_rows"
    assert _raid_field_for("compare.damage.targets.emberkin-0") == "damage_rows"
    assert _raid_field_for("compare.rank.emberkin-0") == "damage_rows"


def test_no_broader_prefix_sits_ahead_of_a_narrower_one() -> None:
    """`PLACEMENTS` resolves by first match, so order is the whole rule.

    A broader prefix ahead of a narrower one silently wins and files a row on
    the wrong tab. `defensives.unused.` is a death-shaped claim and must beat
    the bare `defensives.`; the shared table documents exactly this hazard.
    """
    for index, (prefix, _) in enumerate(RAID_PLACEMENTS):
        for later_prefix, _ in RAID_PLACEMENTS[index + 1:]:
            assert not later_prefix.startswith(prefix) or later_prefix == prefix, (
                f"{later_prefix!r} is narrower than {prefix!r} but sits after it"
            )


KIRILLITSA = Player(
    actor_id=14, name="Кириллица", class_name="Mage", spec="Arcane", item_level=700
)
RICH_PLAYERS = RAID + (KIRILLITSA,)
"""`RAID` is `test_encounter_service`'s own three (Emberkin, Stonewake, Bríala),
reused so the parse-axis subjects built from `RAID`/`RAID_SLUGS` below name the
same players this fixture's roster carries. Кириллица is the one extra raider
this fixture needs and that module does not: a fourth death to pair into a
chain with Bríala's, so Emberkin's two deaths can be an isolated repeat rather
than a chain link."""

RICH_DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=235450, name="Prismatic Barrier", cooldown_seconds=30.0
                ),
                DefensiveAbility(ability_id=45438, name="Ice Block", cooldown_seconds=240.0),
            ),
        ),
    )
)

RICH_CONSUMABLES = Consumables(
    categories=(
        ConsumableCategory(name="Health Potion", cooldown_seconds=300.0, ability_ids=(890,)),
    )
)


FROSTBOLT = 116
FIREBALL = 133
FROST_NOVA = 122
SELF_BUFF = 1459
UNJUDGED_BUFF = 130

REFERENCE_ABILITY_COUNTS = (
    # Never cast by Emberkin at all -> compare.spells.missing.
    (FROSTBOLT, "Frostbolt", 5),
    # Emberkin's own rate sits far below this -> compare.spells.rate.
    (ARCANE_BLAST, "Arcane Blast", 14),
    # Emberkin's own rate sits far above this -> compare.spells.above.
    (FIREBALL, "Fireball", 4),
    # Emberkin's own rate sits inside the band either verdict needs -> compare.spells.level.
    (FROST_NOVA, "Frost Nova", 6),
)
"""One ability per spell verdict `_rate_sample` can reach, cast by all five
reference members alike so every one clears `MIN_MEMBERS_WITH_ABILITY`."""


def _reference_member(report_code: str) -> ParseMember:
    """One reference parse: four abilities and two self buffs.

    Modelled on `test_encounter_service.a_parse_member`, which casts one
    ability and carries no aura data -- this fixture needs one ability per
    spell verdict and an uptime gap and an unjudged buff besides, so it is
    adapted here rather than reused as-is.
    """
    actor_id = 90
    casts = tuple(
        CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name=name,
                  timestamp_ms=one * 1_000)
        for ability_id, name, count in REFERENCE_ABILITY_COUNTS
        for one in range(count)
    )
    auras = PlayerAuras(
        actor_id=actor_id,
        on_self=(
            # Up for most of the reference's own boss time; paired with
            # Emberkin's much shorter band below, the gap clears
            # `UPTIME_GAP_FRACTION` -> compare.uptime.self.
            Aura(ability_id=SELF_BUFF, name="Arcane Intellect", total_uptime_ms=200_000,
                 uses=1, bands=(AuraBand(start_ms=0, end_ms=200_000),)),
            # Carried by every reference and by Emberkin not at all -> compare.uptime.unjudged.
            Aura(ability_id=UNJUDGED_BUFF, name="Mana Shield", total_uptime_ms=100_000,
                 uses=1, bands=(AuraBand(start_ms=0, end_ms=100_000),)),
        ),
    )
    return ParseMember(
        character_name="Stonewake", report_code=report_code, fight_id=1, boss_seconds=240.0,
        players=(
            Player(actor_id=actor_id, name="Stonewake", class_name="Mage", spec="Arcane",
                   item_level=710),
        ),
        casts=casts, auras=auras,
    )


RICH_SAMPLE = ParseSample(members=tuple(_reference_member(f"REF{one}") for one in range(5)))

OUR_SPELL_CASTS = (
    # 4 over the whole 499s fight versus the sample's 14 over 240s: far below.
    *(
        CastEvent(actor_id=11, ability_id=ARCANE_BLAST, ability_name="Arcane Blast",
                  timestamp_ms=2_000 + one * 1_000)
        for one in range(4)
    ),
    # 60 over the fight versus the sample's 4 over 240s: far above.
    *(
        CastEvent(actor_id=11, ability_id=FIREBALL, ability_name="Fireball",
                  timestamp_ms=6_000 + one * 1_000)
        for one in range(60)
    ),
    # 12 over the fight versus the sample's 6 over 240s: inside the band.
    *(
        CastEvent(actor_id=11, ability_id=FROST_NOVA, ability_name="Frost Nova",
                  timestamp_ms=70_000 + one * 1_000)
        for one in range(12)
    ),
    # Frostbolt: never cast, by Emberkin, anywhere.
)

OUR_AURAS = PlayerAuras(
    actor_id=11,
    on_self=(
        # 50s of 499 beside the sample's 200 of 240 -- short enough to gap.
        Aura(ability_id=SELF_BUFF, name="Arcane Intellect", total_uptime_ms=50_000, uses=1,
             bands=(AuraBand(start_ms=0, end_ms=50_000),)),
        # UNJUDGED_BUFF is absent from Emberkin's own auras entirely.
    ),
)

MECHANICS_SAMPLE = MechanicsSample(
    members=(
        MechanicsMember(
            row=ReferenceKillRow(report_code="ref", fight_id=1, size=20, duration_ms=120_000,
                                  deaths=0),
            abilities=(),
        ),
    )
)
"""The one-reference sample `test_encounter_service`'s own mechanics test uses --
below `MIN_SAMPLE_FOR_AGGREGATE`, so `compare_mechanics` still runs against a
single kill rather than a median, exactly as that test proves it does."""

OUR_ABILITIES_TAKEN = (
    AbilityTakenRow(ability_id=400, ability_name="Ravenous Feast", hit_count=12,
                     source_types=("Boss",)),
)


def a_rich_encounter() -> list[Finding]:
    """Every family `analyse_encounter` can emit from one kill without phases.

    A kill, four raiders, five deaths shaped into a single, a chain and a
    repeat, one outlier hit, one landed enemy cast, a defensive and a
    consumable left off cooldown at a death, a mechanics sample, and two
    compared raiders: Emberkin compared in full against a five-member parse
    sample and Stonewake compared with an empty one, which withholds her parse
    axis rather than running it -- `compare.parse.unavailable` is a real
    outcome of comparing her, not a family this fixture skips comparing at all.

    Calls `analyse_encounter` itself and hands back its findings, rather than
    the arguments to call it with: `mechanics` and `parse_subjects` are
    keyword-only, so a caller that can only splat positional arguments could
    never supply them.
    """
    encounter = Encounter(
        report_code="RICH1", fight_id=7, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=500_000,
        players=RICH_PLAYERS,
    )
    casts = (
        # Stonewake's one press of a 30s cooldown, long before her death: below
        # the ceiling `analyse_defensive_ceiling` computes, and off cooldown again by
        # the time `analyse_defensives_at_death` looks.
        CastEvent(actor_id=12, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000),
        # Emberkin's one Health Potion, long before her second death: off
        # cooldown again by then, and never touched by Stonewake, Bríala or
        # Кириллица at all.
        CastEvent(actor_id=11, ability_id=890, ability_name="Health Potion",
                  timestamp_ms=5_000),
        *OUR_SPELL_CASTS,
    )
    # Every killing blow carries its ability id as a real log's does. Without
    # one the id defaults to zero, which is how the log records a death it
    # names no killing ability for -- `compare_lethal_abilities` leaves those
    # out, so a fixture omitting the ids would stop emitting the family
    # altogether. The ids are the ones the damage events below already use.
    deaths = (
        # Isolated in time: a single, and the first of Emberkin's two deaths.
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", killing_blow_id=400,
              seconds_until_next_action=5.0, pull_index=None),
        # Five seconds apart: one chain of two.
        Death(actor_id=13, player_name="Bríala", timestamp_ms=150_000,
              killing_blow="Venomous Bite", killing_blow_id=401,
              seconds_until_next_action=2.0, pull_index=None),
        Death(actor_id=14, player_name="Кириллица", timestamp_ms=155_000,
              killing_blow="Venomous Bite", killing_blow_id=401,
              seconds_until_next_action=2.0, pull_index=None),
        # Isolated, far past her one Prismatic Barrier cast: a single, a
        # defensives.ceiling and a defensives.unused all at once.
        Death(actor_id=12, player_name="Stonewake", timestamp_ms=300_000,
              killing_blow="Ravenous Feast", killing_blow_id=400,
              seconds_until_next_action=4.0, pull_index=None),
        # Isolated, far past her one Health Potion: Emberkin's second death,
        # her repeat, and a consumables.unused.
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=450_000,
              killing_blow="Ravenous Feast", killing_blow_id=400,
              seconds_until_next_action=5.0, pull_index=None),
    )
    damage_taken = (
        # Emberkin takes four times the other three's Ravenous Feast: an
        # outlier against their shared median.
        DamageTakenEvent(actor_id=11, ability_id=400, ability_name="Ravenous Feast",
                          amount=400, timestamp_ms=2_000),
        DamageTakenEvent(actor_id=12, ability_id=400, ability_name="Ravenous Feast",
                          amount=100, timestamp_ms=2_000),
        DamageTakenEvent(actor_id=13, ability_id=400, ability_name="Ravenous Feast",
                          amount=100, timestamp_ms=2_000),
        DamageTakenEvent(actor_id=14, ability_id=400, ability_name="Ravenous Feast",
                          amount=100, timestamp_ms=2_000),
        # Lands within the enemy cast's own follow window, below.
        DamageTakenEvent(actor_id=12, ability_id=999, ability_name="Void Bolt",
                          amount=50_000, timestamp_ms=21_600),
    )
    enemy_cast_rows = (
        EnemyCastRow(source_id=500, source_instance=1, ability_id=999,
                      ability_name="Void Bolt", timestamp_ms=20_000, is_start=True),
        EnemyCastRow(source_id=500, source_instance=1, ability_id=999,
                      ability_name="Void Bolt", timestamp_ms=21_500, is_start=False),
    )
    # Emberkin only: Stonewake's name is deliberately absent from both rows, so
    # her own rank and damage comparisons resolve to their own "unavailable"
    # rows rather than a name-collision or a shared-row finding -- neither of
    # which this fixture is testing.
    standing = a_standing(1_450_000.0, 62)
    boss_standing = a_standing(1_180_000.0, 48)
    loaded = LoadedEncounter(
        encounter=encounter, casts=casts, deaths=deaths,
        enemy_cast_rows=enemy_cast_rows, damage_taken=damage_taken,
        standing=standing, boss_standing=boss_standing,
    )
    parse_subjects = (
        # Compared in full: a real sample, real auras, and the board and
        # target rows `a_parse_subject`'s own defaults already populate.
        a_parse_subject(sample=RICH_SAMPLE, our_auras=OUR_AURAS),
        # Compared with an empty sample: the frame runs and is withheld,
        # which is what produces compare.parse.unavailable.
        ParseSubject(
            player=RAID[1], slug=RAID_SLUGS[RAID[1].actor_id], display_name="Stonewake",
        ),
    )
    return analyse_encounter(
        loaded, RICH_DEFENSIVES, RICH_CONSUMABLES,
        mechanics=MECHANICS_SAMPLE, our_abilities=OUR_ABILITIES_TAKEN,
        parse_subjects=parse_subjects,
    )


def test_the_new_mechanics_families_land_where_the_old_one_does() -> None:
    """`RAID_PLACEMENTS` carries a bare `mechanics.` prefix, so both new
    families route themselves. This test fails if someone narrows it.

    Written against `_raid_field_for` rather than a new `_tab_for` wrapper:
    the module already exposes exactly this lookup under that name, and a
    second helper wrapping it would duplicate the thing this test is meant
    to hold against drift.
    """
    assert (
        _raid_field_for("mechanics.lethal.0")
        == _raid_field_for("mechanics.ability.0")
        == "mechanics_rows"
    )
    assert _raid_field_for("mechanics.phase.0") == "mechanics_rows"


def test_a_verdict_is_claimed_by_no_tab_prefix() -> None:
    """`wipe.cause` matches no prefix and falls through to Summary's unclaimed
    observations, which is where Layer 1 wants it. Layer 2 promotes it to a
    headline; until then this asserts it is not silently swallowed elsewhere.
    """
    assert _raid_field_for("wipe.cause") is None


def test_the_family_list_matches_what_the_service_emits() -> None:
    """Holds `RAID_FAMILIES` against the service, so the list cannot go stale.

    Built from a fixture rich enough to emit every family -- a kill, two
    compared raiders, deaths, a mechanics sample. A family the fixture cannot
    reach is a family this test does not cover, so the assertion is that the
    service emits exactly the families the list carries: not one the list
    forgot, and not one the list carries that nothing emits.
    """
    findings = a_rich_encounter()
    emitted = {_family(finding.id) for finding in findings}
    known = {_family(known) for known in RAID_FAMILIES}
    assert emitted, "the fixture emitted no findings to check against RAID_FAMILIES"
    assert emitted == known, (
        f"missing from RAID_FAMILIES: {sorted(known - emitted)}; "
        f"emitted but not in RAID_FAMILIES: {sorted(emitted - known)}"
    )

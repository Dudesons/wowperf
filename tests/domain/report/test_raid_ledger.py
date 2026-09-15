# ABOUTME: Every raid finding family lands on a tab somebody chose, or on a raider's card.
# ABOUTME: Holds the registry against the service so a new family cannot go silently unplaced.

from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, EnemyCastRow
from wowperf.domain.model import Player
from wowperf.domain.report.raid_ledger import (
    RAID_COMPARISON_PREFIXES,
    RAID_PLACEMENTS,
    _raid_field_for,
)
from wowperf.domain.season import ConsumableCategory, Consumables, DefensiveAbility, Defensives

RAID_FAMILIES = (
    "deaths.total", "deaths.single.0", "deaths.chain.0", "deaths.repeat.emberkin",
    "defensives.never.emberkin.0", "defensives.ceiling.emberkin.0",
    "defensives.unused.emberkin", "consumables.never.emberkin",
    "consumables.unused.emberkin", "interrupts.summary", "interrupts.ability.0",
    "mechanics.ability.0", "players.damage.0",
    "compare.damage.total.emberkin-0", "compare.damage.targets.emberkin-0",
    "compare.rank.emberkin-0", "compare.parse.unavailable.emberkin-0",
    "compare.spells.missing.0.emberkin-0", "compare.spells.rate.0.emberkin-0",
    "compare.spells.above.0.emberkin-0", "compare.spells.level.emberkin-0",
    "compare.talents.emberkin-0", "compare.uptime.self.0.emberkin-0",
    "compare.uptime.unjudged.emberkin-0",
)
"""Every family `analyse_encounter` can emit, as it is emitted after Task 2.

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
    "defensives.never.",
    "defensives.ceiling.",
    "defensives.unused.",
    "consumables.never.",
    "consumables.unused.",
    "interrupts.summary",
    "interrupts.ability.",
    "mechanics.ability.",
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


RICH_PLAYERS = (
    Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=12, name="Stonewake", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=13, name="Bríala", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=14, name="Кириллица", class_name="Mage", spec="Arcane", item_level=700),
)

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


def a_rich_encounter() -> tuple[LoadedEncounter, Defensives, Consumables]:
    """A fight built to reach every family `analyse_encounter` can emit with no
    external comparison sample: a kill, four raiders, five deaths shaped into a
    single, a chain and a repeat, one outlier hit, one landed enemy cast, and
    both a defensive and a consumable left off cooldown at a death.

    `analyse_encounter`'s `mechanics` and `parse_subjects` are keyword-only, so
    `analyse_encounter(*a_rich_encounter())` can only ever supply its three
    positional arguments -- this fixture reaches every family that does not
    need an external sample rather than a partial slice of one that does.
    """
    encounter = Encounter(
        report_code="RICH1", fight_id=7, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=500_000,
        players=RICH_PLAYERS,
    )
    casts = (
        # Stonewake's one press of a 30s cooldown, long before her death: below
        # the ceiling `analyse_defensives` computes, and off cooldown again by
        # the time `analyse_defensives_at_death` looks.
        CastEvent(actor_id=12, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000),
        # Emberkin's one Health Potion, long before her second death: off
        # cooldown again by then, and never touched by Stonewake, Bríala or
        # Кириллица at all.
        CastEvent(actor_id=11, ability_id=890, ability_name="Health Potion",
                  timestamp_ms=5_000),
    )
    deaths = (
        # Isolated in time: a single, and the first of Emberkin's two deaths.
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=5.0,
              pull_index=None),
        # Five seconds apart: one chain of two.
        Death(actor_id=13, player_name="Bríala", timestamp_ms=150_000,
              killing_blow="Venomous Bite", seconds_until_next_action=2.0,
              pull_index=None),
        Death(actor_id=14, player_name="Кириллица", timestamp_ms=155_000,
              killing_blow="Venomous Bite", seconds_until_next_action=2.0,
              pull_index=None),
        # Isolated, far past her one Prismatic Barrier cast: a single, a
        # defensives.ceiling and a defensives.unused all at once.
        Death(actor_id=12, player_name="Stonewake", timestamp_ms=300_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=4.0,
              pull_index=None),
        # Isolated, far past her one Health Potion: Emberkin's second death,
        # her repeat, and a consumables.unused.
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=450_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=5.0,
              pull_index=None),
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
    loaded = LoadedEncounter(
        encounter=encounter, casts=casts, deaths=deaths,
        enemy_cast_rows=enemy_cast_rows, damage_taken=damage_taken,
    )
    return loaded, RICH_DEFENSIVES, RICH_CONSUMABLES


def test_the_family_list_matches_what_the_service_emits() -> None:
    """Holds `RAID_FAMILIES` against the service, so the list cannot go stale.

    Built from a fixture rich enough to emit every family -- a kill, two
    compared raiders, deaths, a mechanics sample. A family the fixture cannot
    reach is a family this test does not cover, so the assertion is that the
    service emits nothing outside the list, and the guard below is that the
    fixture emitted a useful number of families at all.
    """
    findings = analyse_encounter(*a_rich_encounter())
    emitted = {_family(finding.id) for finding in findings}
    assert len(emitted) >= 8, sorted(emitted)
    assert emitted <= {_family(known) for known in RAID_FAMILIES}, sorted(
        emitted - {_family(known) for known in RAID_FAMILIES}
    )

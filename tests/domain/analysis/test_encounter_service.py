# ABOUTME: The raid analyser list, and which claims a boss fight can support.
# ABOUTME: What is absent here matters as much as what is present.

from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.comparison.mechanics import (
    AbilityTakenRow,
    MechanicsMember,
    MechanicsSample,
    ReferenceKillRow,
)
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
from wowperf.domain.season import Consumables, DefensiveAbility, Defensives, Roles

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=235450, name="Prismatic Barrier", cooldown_seconds=30.0
                ),
            ),
        ),
    )
)


def a_loaded_encounter(**overrides: object) -> LoadedEncounter:
    encounter = Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=375_000,
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=700),
        ),
    )
    fields: dict[str, object] = {"encounter": encounter}
    fields.update(overrides)
    return LoadedEncounter(**fields)  # type: ignore[arg-type]


def test_a_fight_with_nothing_in_it_produces_only_never_cast_defensives() -> None:
    """An empty fight invents nothing it lacks data for -- but that is not `[]`.

    `analyse_defensives` states, once, that Prismatic Barrier was never cast --
    a real claim this fixture's zero casts support (`analyse_defensives`' never-
    cast branch emits it for every ability in a player's spec the player never
    pressed). What must stay absent is anything needing data an empty fight has
    none of: a death, a landed or kicked enemy cast, a consumable, or a
    ceiling computed from an actual cast.
    """
    findings = analyse_encounter(a_loaded_encounter(), DEFENSIVES, Consumables())

    assert findings, "an uncast defensive is a real, reportable claim, not silence"
    assert all(f.id.startswith("defensives.never.") for f in findings)
    forbidden = ("deaths.", "interrupts.", "consumables.", "defensives.ceiling.")
    leaked = [f.id for f in findings if f.id.startswith(forbidden)]
    assert leaked == [], f"needs data an empty fight does not have: {leaked}"


def test_a_death_is_reported_and_located_against_the_fight() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())

    assert findings, "a death must produce a finding"
    # deaths.total and defensives.never.* both reach rank_findings; deaths.total
    # carries a seconds_lost and defensives.never.* does not, so rank_findings'
    # (None-last) key puts it first deterministically, not by insertion luck.
    assert findings[0].id == "deaths.total"
    assert any("The Twin Fangs" in line for line in findings[0].evidence)
    assert not any("pull" in line for f in findings for line in f.evidence)
    # A boss fight has no timer penalty and no time decomposition to point a
    # reader at -- decompose_time is deliberately absent from analyse_encounter.
    assert "timer penalty" not in findings[0].detail
    assert "time decomposition" not in findings[0].detail


def test_the_defensive_ceiling_uses_fight_duration_and_therefore_fires() -> None:
    """The regression this whole slice guards against.

    Under the rejected design -- a Run holding one degenerate pull -- the
    ceiling denominator was zero and this finding disappeared in silence.

    Prismatic Barrier (235450, 30s cooldown -- data/defensives.toml:139) is used
    rather than Ice Block: in a 374s fight Ice Block's 240s cooldown yields a
    ceiling of 1.56, below `MIN_CEILING_USES = 3.0`, so the finding would be
    suppressed regardless of fight duration and prove nothing about this
    regression. Prismatic Barrier's ceiling is 374 / 30 = 12.5.
    """
    casts = (
        CastEvent(actor_id=11, ability_id=235450, ability_name="Prismatic Barrier",
                  timestamp_ms=10_000, pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(casts=casts), DEFENSIVES,
                                 Consumables())

    ceiling = [f for f in findings if f.id.startswith("defensives.ceiling")]
    assert ceiling, "one Prismatic Barrier cast in a 374s fight is below its ceiling"
    assert ceiling[0].confidence is Confidence.INFERRED


def test_no_keystone_shaped_finding_reaches_a_raid_report() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())
    assert findings, "the guard below proves nothing against an empty list"
    forbidden = ("time.residual", "time.gap", "trash.", "compare.route")
    leaked = [f.id for f in findings if f.id.startswith(forbidden)]
    assert leaked == [], f"Mythic+ findings reached a raid report: {leaked}"


ROLES = Roles(tanks=("Warrior/Protection",))

RAID = (
    Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=12, name="Stonewake", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=13, name="Bríala", class_name="Mage", spec="Arcane", item_level=700),
)


def a_raid_encounter() -> Encounter:
    """Three players and a 120-second fight, so a median has three takers."""
    return Encounter(
        report_code="abc123", fight_id=22, encounter_id=3421,
        boss_name="The Twin Fangs", difficulty=4, partition=1, size=20,
        kill=True, fight_percentage=0.01, start_ms=1_000, end_ms=121_000,
        players=RAID,
    )


def took(actor_id: int, amount: int) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=400, ability_name="Ravenous Feast",
        amount=amount, timestamp_ms=2_000,
    )


def test_the_outlier_finding_now_reaches_a_raid_report() -> None:
    # `roles` stopped being inert with this plan: the outlier half of
    # `analyse_players` is the one piece of it a boss fight supports.
    loaded = a_loaded_encounter(
        encounter=a_raid_encounter(),
        damage_taken=(took(11, 400), took(12, 100), took(13, 100)),
    )
    findings = analyse_encounter(loaded, DEFENSIVES, Consumables(), roles=ROLES)
    assert any(finding.id.startswith("players.damage.") for finding in findings)


def test_a_mechanic_outranks_a_defensive_though_neither_costs_seconds() -> None:
    """Severity, and only severity, can produce this order.

    Both families carry `seconds_lost=None`, and `analyse_encounter` appends
    defensives long before mechanics, so under `rank_findings` the sort is
    stable and defensives come first. Deaths would have been the wrong pair to
    test with: a raid death does carry seconds, so `rank_findings` already
    sorts it above a mechanic and the assertion could not have failed.
    """
    sample = MechanicsSample(
        members=(
            MechanicsMember(
                row=ReferenceKillRow(
                    report_code="ref", fight_id=1, size=20,
                    duration_ms=120_000, deaths=0,
                ),
                abilities=(),
            ),
        )
    )
    ours = (
        AbilityTakenRow(
            ability_id=400, ability_name="Ravenous Feast", hit_count=12,
            source_types=("Boss",),
        ),
    )
    findings = analyse_encounter(
        a_loaded_encounter(encounter=a_raid_encounter()),
        DEFENSIVES, Consumables(), roles=ROLES,
        mechanics=sample, our_abilities=ours,
    )
    families = [finding.id.split(".", 1)[0] for finding in findings]
    assert "mechanics" in families, "the fixture must produce a mechanics finding"
    assert "defensives" in families, "the fixture must produce a defensives finding"
    assert families.index("mechanics") < families.index("defensives")

    # `scope` names who took the landings, not the encounter: "the raid", never
    # the boss. `compare_mechanics`'s title reads "{scope} took N of {ability}",
    # so a `scope` of the boss name would have this read as the boss taking its
    # own damage -- exactly the slip this pins against returning silently.
    [mechanics_finding] = [finding for finding in findings if finding.id.startswith("mechanics")]
    assert mechanics_finding.title.startswith("the raid")
    assert "Twin Fangs" not in mechanics_finding.title

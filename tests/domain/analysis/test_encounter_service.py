# ABOUTME: The raid analyser list, and which claims a boss fight can support.
# ABOUTME: What is absent here matters as much as what is present.

from wowperf.domain.analysis.encounter_service import analyse_encounter
from wowperf.domain.encounter import Encounter, LoadedEncounter
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import Player
from wowperf.domain.season import Consumables, DefensiveAbility, Defensives

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
    a real claim this fixture's zero casts support (defensives.py:299-305 emits
    it for every ability in a player's spec the player never pressed). What
    must stay absent is anything needing data an empty fight has none of: a
    death, a landed or kicked enemy cast, a consumable, or a ceiling computed
    from an actual cast.
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


def test_every_finding_carries_a_confidence_badge() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=61_000,
              killing_blow="Ravenous Feast", seconds_until_next_action=3.0,
              pull_index=None),
    )
    findings = analyse_encounter(a_loaded_encounter(deaths=deaths), DEFENSIVES,
                                 Consumables())
    assert findings, "the guard below proves nothing against an empty list"
    assert all(isinstance(f.confidence, Confidence) for f in findings)


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

# ABOUTME: The death recap and the ledger's ability panels, built from a boss fight not a run.
# ABOUTME: The roster and the window come from whichever fight was handed over, never from a Run.

from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.auras import Aura, AuraBand, PlayerAuras
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.report.deaths import build_deaths
from wowperf.domain.report.finding_tooltip import tooltips_by_finding_id
from wowperf.domain.season import (
    ConsumableCategory,
    Consumables,
    DefensiveAbility,
    Defensives,
)

# A boss fight whose log begins well after zero, which is the whole point: a
# window taken from the fight and a window assumed to start at zero give
# different answers, and only the first is right about a raid night's third pull.
FIGHT_START_MS = 1_000_000
FIGHT_END_MS = 1_600_000

STONEWAKE = Player(
    actor_id=1, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=680
)
ICEBOUND = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=120.0)
HEALTHSTONE = ConsumableCategory(
    name="health potion", cooldown_seconds=300.0, ability_ids=(1234768,)
)

NO_DEFENSIVES = Defensives()
NO_CONSUMABLES = Consumables()
POTIONS = Consumables(categories=(HEALTHSTONE,))
BLOOD = Defensives(entries=(("DeathKnight/Blood", (ICEBOUND,)),))

CEILING_ID = "defensives.ceiling.stonewake.48792"


def a_death(at_ms: int) -> Death:
    return Death(
        player_name="Stonewake", actor_id=1, timestamp_ms=at_ms, killing_blow="Frigid Roar"
    )


def a_hit(at_ms: int, amount: int = 900) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=1, ability_id=1, ability_name="Frigid Roar", amount=amount,
        health_damage=amount, timestamp_ms=at_ms,
    )


def a_loaded_fight(**streams: object) -> LoadedEncounter:
    return LoadedEncounter(
        encounter=an_encounter(
            players=(STONEWAKE,), start_ms=FIGHT_START_MS, end_ms=FIGHT_END_MS
        ),
        **streams,  # type: ignore[arg-type]
    )


def test_a_death_on_a_boss_fight_gets_a_recap_card() -> None:
    """The recap reads a roster and event streams, both of which a boss fight has.

    `build_deaths` reached through `loaded.run` for the roster, which is the one
    thing a `LoadedEncounter` cannot answer: it is a sibling of `LoadedRun` and
    not a subtype, by design section 5.3.
    """
    loaded = a_loaded_fight(deaths=(a_death(1_300_000),), damage_taken=(a_hit(1_295_000),))

    cards = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)

    assert len(cards) == 1, "the fight built no recap card"
    assert cards[0].player == "Stonewake"
    assert cards[0].class_name == "DeathKnight"
    assert [row.ability for row in cards[0].timeline] == ["Frigid Roar"]


def test_a_boss_deaths_time_claims_no_pull_the_fight_never_had() -> None:
    """A boss fight is one continuous window, so there is nothing to be between.

    `_when` appended ", between pulls" whenever a death carried no pull index,
    which is every death of a raid: the card read "2:30, between pulls" about a
    fight that has no pulls to sit between. The elapsed time stands alone here,
    and a fight that does have pulls still names them -- that is the Mythic+
    card, unchanged.
    """
    loaded = a_loaded_fight(deaths=(a_death(FIGHT_START_MS + 150_000),))

    card = build_deaths(loaded, NO_DEFENSIVES, NO_CONSUMABLES)[0]

    assert card.when == "2:30"


def test_a_consumable_is_judged_only_from_the_fights_own_start() -> None:
    """Design section 6.11: `visible_from_ms` becomes the fight's start.

    A category's window opens `cooldown + run-up` before the death -- 310 s for
    this one. The earlier death's window opens 10 s before the fight's log
    begins, so silence about the category proves nothing and the group stays
    empty; the later death's window lies wholly inside the fight and is judged.
    A window taken from zero rather than from the fight would judge both, which
    is the failure this distinguishes.
    """
    drink = CastEvent(
        actor_id=1, ability_id=1234768, ability_name="Healthstone", timestamp_ms=1_100_000
    )
    too_early = a_loaded_fight(deaths=(a_death(1_300_000),), casts=(drink,))
    late_enough = a_loaded_fight(deaths=(a_death(1_400_000),), casts=(drink,))

    early_group = build_deaths(too_early, NO_DEFENSIVES, POTIONS)[0].availability[1]
    late_group = build_deaths(late_enough, NO_DEFENSIVES, POTIONS)[0].availability[1]

    assert late_group.rows, "the judgeable death listed no consumable at all"
    assert [row.ability for row in late_group.rows] == ["health potion"]
    assert early_group.rows == ()


def test_a_defensives_finding_on_a_boss_fight_gets_its_measured_panel() -> None:
    """The ledger's ability panel reads the same roster and window the recap does."""
    loaded = _a_fight_where_icebound_was_pressed()

    tooltips = tooltips_by_finding_id((_a_ceiling_finding(),), loaded, BLOOD)

    assert CEILING_ID in tooltips, sorted(tooltips)
    assert [line.label for line in tooltips[CEILING_ID].lines][:2] == ["Base cooldown", "Presses"]


def test_the_ability_panel_clips_its_cover_at_the_fights_end() -> None:
    """The window ends where the fight does, so a band running past it counts only its part.

    The band below runs ten seconds beyond the last event of the fight. A
    window that ended at the fight's end reports ten seconds of cover; one that
    never ended would report twenty, and one that started at zero would still
    report twenty. Only the first is a statement about this fight.
    """
    loaded = _a_fight_where_icebound_was_pressed()

    panel = tooltips_by_finding_id((_a_ceiling_finding(),), loaded, BLOOD)[CEILING_ID]

    cover = [line.value for line in panel.lines if line.label == "Cover"]
    assert cover, [line.label for line in panel.lines]
    assert cover == ["10.0 s"]


def _a_ceiling_finding() -> Finding:
    return Finding(
        id=CEILING_ID, title="x", detail="detail", confidence=Confidence.INFERRED,
        ability_id=48792, ability_name="Icebound Fortitude",
    )


def _a_fight_where_icebound_was_pressed() -> LoadedEncounter:
    """One press, and an aura band that outlives the fight by ten seconds."""
    return a_loaded_fight(
        casts=(
            CastEvent(
                actor_id=1, ability_id=48792, ability_name="Icebound Fortitude",
                timestamp_ms=1_590_000,
            ),
        ),
        auras=(
            PlayerAuras(actor_id=1, on_self=(
                Aura(
                    ability_id=48792, name="Icebound Fortitude", total_uptime_ms=20_000, uses=1,
                    bands=(AuraBand(start_ms=1_590_000, end_ms=1_610_000),),
                ),
            )),
        ),
    )

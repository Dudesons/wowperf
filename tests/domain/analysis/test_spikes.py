# ABOUTME: The group's heaviest moments of damage taken, and whether a group cooldown answered each.
# ABOUTME: Pins the curve, the ranking, the floor, the answer set, each state and every wording.

import re

from wowperf.domain.analysis.spikes import (
    ANSWER_LEAD_SECONDS,
    NOT_JUDGED_TITLE,
    SPIKES_ID,
    UNANSWERED_ID,
    UNAVAILABLE_ID,
    Answer,
    analyse_spikes,
    answers_for,
    heaviest_moments,
)
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death, Resurrection
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.season import (
    CooldownAbility,
    ExternalAbility,
    Externals,
    Roles,
    ThroughputCooldowns,
)

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
WARRIOR = Player(actor_id=2, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)
MAGE = Player(actor_id=3, name="Bríala", class_name="Mage", spec="Frost", item_level=690)
ROSTER = (DRUID, WARRIOR, MAGE)
PET = 99

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
SWIFTNESS = CooldownAbility(ability_id=132158, name="Nature's Swiftness", cooldown_seconds=60.0)
RALLYING = ExternalAbility(
    ability_id=97462, name="Rallying Cry", cooldown_seconds=180.0, group=True
)
IRONBARK = ExternalAbility(ability_id=102342, name="Ironbark", cooldown_seconds=90.0)

THROUGHPUT = ThroughputCooldowns(
    entries=(("Druid/Restoration", (TRANQUILITY, SWIFTNESS)), ("Mage/Frost", (TRANQUILITY,)))
)
EXTERNALS = Externals(entries=(("Druid/Restoration", (IRONBARK,)), ("Warrior/Arms", (RALLYING,))))
ROLES = Roles(healers=("Druid/Restoration",))
ANSWERS = answers_for(ROSTER, THROUGHPUT, EXTERNALS, ROLES)

FIVE_MINUTES = (0, 300_000)


def hit(actor_id: int, second: float, health: int, *, absorbed: int = 0, overkill: int = 0
        ) -> DamageTakenEvent:
    return DamageTakenEvent(
        actor_id=actor_id, ability_id=1, ability_name="Venom Bolt", amount=health + absorbed,
        timestamp_ms=int(second * 1000), health_damage=health, absorbed=absorbed,
        overkill=overkill,
    )


def steady(seconds: int, per_second: int = 100) -> list[DamageTakenEvent]:
    """The mage taking the same damage every second: the median every burst is weighed by."""
    return [hit(MAGE.actor_id, second, per_second) for second in range(seconds)]


def burst(first: int, *, per_second: int = 1000, length: int = 5) -> list[DamageTakenEvent]:
    return [hit(MAGE.actor_id, first + one, per_second) for one in range(length)]


def cast(player: Player, ability: CooldownAbility, second: float) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability.ability_id, ability_name=ability.name,
        timestamp_ms=int(second * 1000),
    )


FILLER = cast(MAGE, SWIFTNESS, 1)
"""One unrelated cast, so a fight with no answer pressed still reads as a fight with casts."""


def spikes(
    damage: list[DamageTakenEvent],
    casts: list[CastEvent],
    *,
    span: tuple[int, int] = FIVE_MINUTES,
    combat: tuple[tuple[int, int], ...] | None = None,
    deaths: tuple[Death, ...] = (),
    resurrections: tuple[Resurrection, ...] = (),
    answers: tuple[Answer, ...] = ANSWERS,
    setting: str = "fight",
) -> list[Finding]:
    return analyse_spikes(
        damage_taken=damage, casts=casts, deaths=deaths, resurrections=resurrections,
        players=ROSTER, answers=answers, span=span,
        combat=combat if combat is not None else (span,), setting=setting,
    )


def the(findings: list[Finding], finding_id: str) -> Finding:
    [one] = [finding for finding in findings if finding.id == finding_id]
    return one


def test_the_answer_set_is_a_healers_marked_cooldowns_and_anyones_marked_externals() -> None:
    names = [(one.holder, one.ability.name) for one in ANSWERS]
    assert names == [
        ("Restoration Druid, Emberkin", "Tranquility"),
        ("Arms Warrior, Stonewake", "Rallying Cry"),
    ]


def test_a_hit_counts_what_reached_health_and_what_a_shield_took_less_overkill() -> None:
    moments = heaviest_moments(
        [*steady(300), hit(MAGE.actor_id, 100, 700, absorbed=500, overkill=200)],
        frozenset({MAGE.actor_id}), FIVE_MINUTES, (FIVE_MINUTES,),
    )
    [heaviest] = [one for one in moments if one.rank == 1]
    assert heaviest.weight == (500 + 700 + 500 - 200) / 500


def test_a_pet_or_an_npc_taking_damage_is_not_counted() -> None:
    damage = [*steady(300), *(hit(PET, 100 + one, 50_000) for one in range(5))]
    findings = spikes(damage, [FILLER])
    assert the(findings, UNAVAILABLE_ID).title == "No moment of this fight was heavy enough to rank"


def test_a_burst_straddling_a_second_boundary_is_one_whole_window() -> None:
    moments = heaviest_moments(
        [*steady(300), *burst(42)], frozenset({MAGE.actor_id}), FIVE_MINUTES, (FIVE_MINUTES,)
    )
    assert [(one.start_ms, one.end_ms) for one in moments if one.rank == 1] == [(42_000, 47_000)]


def test_one_moment_per_started_three_minutes_heaviest_first_never_overlapping() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540), *burst(100, per_second=3000), *burst(102, per_second=2500),
              *burst(300, per_second=2000), *burst(450, per_second=1500)]
    moments = heaviest_moments(
        damage, frozenset({MAGE.actor_id}), nine_minutes, (nine_minutes,)
    )
    assert [(one.start_ms // 1000, one.rank) for one in moments] == [(100, 1), (300, 2), (450, 3)]


def test_a_window_below_twice_the_median_never_ranks() -> None:
    findings = spikes([*steady(300), *burst(100, per_second=90)], [FILLER])
    assert [one.id for one in findings] == [UNAVAILABLE_ID]


def test_a_window_straddling_two_pulls_neither_ranks_nor_weighs() -> None:
    run = (0, 400_000)
    pulls = ((0, 100_000), (200_000, 300_000))
    damage = [*(hit(MAGE.actor_id, s, 100) for s in (*range(100), *range(200, 300))),
              *burst(98, per_second=5000, length=4)]
    moments = heaviest_moments(damage, frozenset({MAGE.actor_id}), run, pulls)
    assert all(
        any(low <= one.start_ms and one.end_ms <= high for low, high in pulls) for one in moments
    )
    assert [one.weight for one in moments if one.rank == 1] == [(100 * 5 + 5000 * 2) / 500]


def test_a_press_up_to_the_lead_before_the_window_answers_it() -> None:
    before = 200 - ANSWER_LEAD_SECONDS
    findings = spikes([*steady(300), *burst(200)], [FILLER, cast(DRUID, TRANQUILITY, before)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): answered by Tranquility "
        "(Restoration Druid, Emberkin)",
    )


def test_a_press_one_second_earlier_than_the_lead_is_not_an_answer() -> None:
    before = 200 - ANSWER_LEAD_SECONDS - 1
    findings = spikes([*steady(300), *burst(200)], [FILLER, cast(DRUID, TRANQUILITY, before)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready; Tranquility (Restoration Druid, Emberkin): pressed at 3:09, within its "
        "base cooldown of 3:00",
    )


def test_a_cooldown_ready_and_unpressed_is_held_against_the_group() -> None:
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5), cast(WARRIOR, RALLYING, 100)]
    findings = spikes([*steady(300), *burst(200)], casts)
    assert the(findings, SPIKES_ID).title == (
        "1 heaviest moment: 1 unanswered while cooldowns were ready"
    )
    unanswered = the(findings, UNANSWERED_ID)
    assert unanswered.confidence is Confidence.INFERRED
    assert unanswered.title == (
        "1 of 1 heaviest moment went unanswered while group cooldowns were ready"
    )
    assert unanswered.evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed; ready: Tranquility "
        "(Restoration Druid, Emberkin)",
    )


def test_a_cooldown_whose_window_reaches_before_the_fight_is_not_judged() -> None:
    findings = spikes([*steady(300), *burst(42)], [FILLER, cast(DRUID, TRANQUILITY, 250)])
    assert UNANSWERED_ID not in [one.id for one in findings]
    assert the(findings, SPIKES_ID).evidence == (
        "0:42 to 0:47, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready; Tranquility (Restoration Druid, Emberkin): not judged, its base cooldown "
        "reaches before the fight's first second",
    )


def test_a_cooldown_never_pressed_all_fight_is_not_seen_at_all() -> None:
    findings = spikes([*steady(300), *burst(200)], [FILLER])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (11.0 times the median): nothing pressed, and no answer was "
        "shown ready",
    )


def test_a_holder_dead_when_the_window_opens_is_not_counted_ready() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=190_000,
                 killing_blow="Venom Bolt")
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,))
    assert UNANSWERED_ID not in [one.id for one in findings]
    assert the(findings, SPIKES_ID).evidence[0].endswith(
        "Tranquility (Restoration Druid, Emberkin): its holder was dead"
    )


def test_a_holder_brought_back_before_the_window_is_alive_again() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=150_000,
                 killing_blow="Venom Bolt")
    back = Resurrection(actor_id=DRUID.actor_id, caster_id=WARRIOR.actor_id, ability_id=20484,
                        ability_name="Rebirth", timestamp_ms=170_000)
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,), resurrections=(back,))
    assert UNANSWERED_ID in [one.id for one in findings]


def test_a_cast_after_a_death_is_as_good_a_sign_of_life_as_a_resurrection() -> None:
    died = Death(player_name=DRUID.name, actor_id=DRUID.actor_id, timestamp_ms=150_000,
                 killing_blow="Venom Bolt")
    casts = [FILLER, cast(DRUID, TRANQUILITY, 5), cast(DRUID, SWIFTNESS, 180)]
    findings = spikes([*steady(300), *burst(200)], casts, deaths=(died,))
    assert UNANSWERED_ID in [one.id for one in findings]


def test_the_title_counts_every_state_that_occurred_in_a_fixed_order() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540), *burst(100, per_second=3000), *burst(300, per_second=2000),
              *burst(450, per_second=1500)]
    casts = [FILLER, cast(DRUID, TRANQUILITY, 98), cast(WARRIOR, RALLYING, 60)]
    findings = spikes(damage, casts, span=nine_minutes)
    assert the(findings, SPIKES_ID).title == (
        "3 heaviest moments: 1 answered, 2 unanswered while cooldowns were ready"
    )
    assert the(findings, SPIKES_ID).confidence is Confidence.DERIVED
    assert [line.split(",")[0] for line in the(findings, SPIKES_ID).evidence] == [
        "1:40 to 1:45", "5:00 to 5:05", "7:30 to 7:35",
    ]
    assert "the second heaviest" in the(findings, SPIKES_ID).evidence[1]


def test_a_run_read_without_casts_says_so() -> None:
    findings = spikes([*steady(300), *burst(200)], [], setting="run")
    assert [(one.id, one.title, one.detail) for one in findings] == [(
        UNAVAILABLE_ID, NOT_JUDGED_TITLE,
        "This run was read without its casts, so no press of any cooldown can be seen.",
    )]
    assert findings[0].confidence is Confidence.MEASURED


def test_a_group_holding_no_answer_says_so() -> None:
    findings = spikes([*steady(300), *burst(200)], [FILLER], answers=())
    assert [(one.id, one.title) for one in findings] == [(UNAVAILABLE_ID, NOT_JUDGED_TITLE)]
    assert "whole group's damage" in findings[0].detail


def test_a_median_of_nothing_names_no_multiple() -> None:
    findings = spikes(burst(200), [FILLER, cast(DRUID, TRANQUILITY, 200)])
    assert the(findings, SPIKES_ID).evidence == (
        "3:20 to 3:25, the heaviest (most of this fight's 5-second windows took no damage): "
        "answered by Tranquility (Restoration Druid, Emberkin)",
    )


def test_no_title_detail_or_evidence_carries_a_raw_damage_figure() -> None:
    nine_minutes = (0, 540_000)
    damage = [*steady(540, per_second=40_000), *burst(100, per_second=900_000),
              *burst(300, per_second=500_000)]
    casts = [FILLER, cast(DRUID, TRANQUILITY, 98), cast(WARRIOR, RALLYING, 60)]
    for finding in spikes(damage, casts, span=nine_minutes):
        for text in (finding.title, finding.detail, *finding.evidence):
            assert not re.search(r"\d{4,}", text), text

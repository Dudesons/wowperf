# ABOUTME: The Healers group on a death card: one line per other healer, every sentence pinned.
# ABOUTME: Fixtures sit on a non-zero clock origin, as report timestamps do.

import re

from tests.domain.report.test_build_frame import NO_CONSUMABLES, NO_DEFENSIVES, a_pull, a_run
from wowperf.domain.events import CastEvent, DamageTakenEvent, Death
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.deaths import (
    HEALER_AIM,
    HEALER_LANDED,
    NO_OTHER_HEALER,
    build_deaths,
)
from wowperf.domain.report.model import DeathCard, HealerGroup
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns

ORIGIN = 3_000_000

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
PRIEST = Player(actor_id=2, name="Bríala", class_name="Priest", spec="Holy", item_level=690)
WARRIOR = Player(actor_id=3, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)
UNKNOWN = Player(actor_id=4, name="Кириллица", class_name="Mage", spec="", item_level=690)
GHOST = Player(actor_id=5, name="Briala", class_name="Rogue", spec="", item_level=690)

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
THROUGHPUT = ThroughputCooldowns(entries=(("Druid/Restoration", (TRANQUILITY,)),))
ROLES = Roles(healers=("Druid/Restoration", "Priest/Holy"))
ENEMY = 900


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def cast(player: Player, second: float, target: int | None, ability_id: int = 774) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability_id, ability_name="Rejuvenation",
        timestamp_ms=at(second), target_id=target,
    )


def death_of(player: Player, second: float) -> Death:
    return Death(player_name=player.name, actor_id=player.actor_id, timestamp_ms=at(second),
                 killing_blow="Venom Bolt", pull_index=0)


def card_for(
    casts: list[CastEvent],
    *,
    roster: tuple[Player, ...] = (DRUID, WARRIOR),
    deaths: tuple[Death, ...] = (),
    dying: Player = WARRIOR,
    second: float = 300,
    roles: Roles | None = ROLES,
    trimmed: bool = False,
    damage_taken: tuple[DamageTakenEvent, ...] = (),
) -> DeathCard:
    death = death_of(dying, second)
    loaded = LoadedRun(
        run=a_run(players=roster, pulls=(a_pull(0, ORIGIN, at(600)),)),
        deaths=(*deaths, death),
        casts=tuple(casts),
        damage_taken=damage_taken,
    )
    cards = build_deaths(
        loaded, NO_DEFENSIVES, NO_CONSUMABLES, roles=roles, throughput=THROUGHPUT,
        trimmed=trimmed,
    )
    [card] = [one for one in cards if one.player == dying.name]
    return card


def healers_of(card: DeathCard) -> HealerGroup:
    assert card.healers is not None
    return card.healers


def test_a_card_built_without_roles_draws_no_healers_group() -> None:
    assert card_for([], roles=None).healers is None


def test_a_healers_line_names_the_holder_and_counts_casts_by_aim() -> None:
    casts = [
        cast(DRUID, 291, WARRIOR.actor_id), cast(DRUID, 292, WARRIOR.actor_id),
        cast(DRUID, 293, DRUID.actor_id), cast(DRUID, 295, ENEMY), cast(DRUID, 296, None),
        cast(DRUID, 20, None, ability_id=740),
    ]
    [line] = healers_of(card_for(casts)).lines
    assert line.holder == "Restoration Druid, Emberkin"
    assert line.summary == (
        "alive when this player died; 5 casts in the last 10 seconds: 2 at this player, "
        "1 at themselves, 1 at a non-player, 1 untargeted; the last at this player 8.0 s "
        "before death"
    )


def test_casts_at_other_players_are_counted_in_the_plural() -> None:
    casts = [cast(DRUID, 293, PRIEST.actor_id), cast(DRUID, 294, PRIEST.actor_id)]
    group = healers_of(card_for(casts, roster=(DRUID, PRIEST, WARRIOR)))
    assert [line.summary for line in group.lines][0] == (
        "alive when this player died; 2 casts in the last 10 seconds: 2 at other players; "
        "none at this player"
    )


def test_a_healer_casting_nothing_in_the_run_up_says_so() -> None:
    [line] = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)])).lines
    assert line.summary == "alive when this player died; no cast in the last 10 seconds"


def test_each_cooldown_reading_is_worded_back_from_the_death() -> None:
    ready = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)])).lines[0]
    pressed = healers_of(card_for([cast(DRUID, 297, None, ability_id=740)])).lines[0]
    within = healers_of(card_for([cast(DRUID, 190, None, ability_id=740)])).lines[0]
    unjudged = healers_of(card_for([cast(DRUID, 250, None, ability_id=740)], second=100)).lines[0]
    assert [(row.ability, row.state, row.detail) for row in ready.cooldowns] == [
        ("Tranquility", "ready", "ready")
    ]
    assert [row.detail for row in pressed.cooldowns] == ["pressed 3.0 s before death"]
    assert [row.detail for row in within.cooldowns] == [
        "pressed 1:50 before death, within its base cooldown of 3:00"
    ]
    assert [(row.state, row.detail) for row in unjudged.cooldowns] == [
        ("unjudged", "not judged, its base cooldown reaches before the run's first second")
    ]


def test_a_press_before_the_first_pull_is_timed_back_from_the_death() -> None:
    pre_pull = cast(DRUID, -15, None, ability_id=740)
    [line] = healers_of(card_for([pre_pull], second=100)).lines
    assert [row.detail for row in line.cooldowns] == [
        "pressed 1:55 before death, within its base cooldown of 3:00"
    ]


def test_a_dead_healer_says_when_they_died_and_what_they_held_as_the_damage_began() -> None:
    # "Dead" is read from a death with no resurrection and no cast since, so the
    # line says that much and no more: on a key a healer who released is back at
    # the entrance, alive, and reads this way until they cast.
    casts = [cast(DRUID, 20, None, ability_id=740)]
    [line] = healers_of(card_for(casts, deaths=(death_of(DRUID, 250),))).lines
    assert line.summary == (
        "died 50.0 s before this player, not seen acting since; no cast in the last 10 seconds"
    )
    assert [(row.ability, row.state, row.detail) for row in line.cooldowns] == [
        ("Tranquility", "dead", "its holder was dead when the damage began")
    ]
    assert line.note == ""


def test_a_healer_who_pressed_a_group_cooldown_then_died_shows_the_press() -> None:
    casts = [cast(DRUID, 292, None, ability_id=740)]
    [line] = healers_of(card_for(casts, deaths=(death_of(DRUID, 295),))).lines
    assert line.summary.startswith("died 5.0 s before this player, not seen acting since; ")
    assert [(row.ability, row.state, row.detail) for row in line.cooldowns] == [
        ("Tranquility", "pressed", "pressed 8.0 s before death")
    ]


def test_a_dead_healer_whose_cooldowns_were_never_pressed_says_so_as_anyone_would() -> None:
    [line] = healers_of(card_for([], deaths=(death_of(DRUID, 250),))).lines
    assert (line.cooldowns, line.note) == (
        (), "None of their group healing cooldowns was pressed in the log read for this run."
    )


def test_a_cooldown_dead_when_the_run_up_opens_reads_dead_though_its_holder_revived() -> None:
    # The druid died at 285 and cast nothing more until 296, so the run-up opens
    # at 290 with them still dead: Tranquility, last pressed at 20, reads DEAD.
    # The 296 cast is itself a sign of life, so the healer is alive by the death
    # at 300 -- the two questions read from different instants and can disagree.
    casts = [
        cast(DRUID, 20, None, ability_id=740), cast(DRUID, 296, WARRIOR.actor_id),
    ]
    [line] = healers_of(card_for(casts, deaths=(death_of(DRUID, 285),))).lines
    assert line.summary == (
        "alive when this player died; 1 cast in the last 10 seconds: 1 at this player; "
        "the last at this player 4.0 s before death"
    )
    assert [(row.ability, row.state, row.detail) for row in line.cooldowns] == [
        ("Tranquility", "dead", "its holder was dead when the damage began")
    ]


def test_a_healer_whose_cooldowns_were_never_pressed_says_so_in_one_clause() -> None:
    [line] = healers_of(card_for([cast(DRUID, 295, None)])).lines
    assert line.cooldowns == ()
    assert line.note == (
        "None of their group healing cooldowns was pressed in the log read for this run."
    )


def test_a_healer_whose_spec_lists_no_group_cooldown_says_so() -> None:
    group = healers_of(card_for([], roster=(PRIEST, WARRIOR)))
    assert group.lines[0].note == "No group healing cooldown is listed for Holy Priest."


def test_with_no_other_healer_the_group_holds_one_sentence() -> None:
    group = healers_of(card_for([], dying=DRUID))
    assert (group.lines, group.note, group.badge) == ((), NO_OTHER_HEALER, None)


def test_with_no_other_healer_and_an_unknown_specialisation_the_note_says_so() -> None:
    group = healers_of(card_for([], roster=(DRUID, WARRIOR, UNKNOWN), dying=DRUID))
    assert (group.lines, group.badge) == ((), None)
    assert group.note == (
        "No other player's specialisation reads as a healer's, and the log names no "
        "specialisation for 1 other player: a healer among them would not be listed."
    )


def test_the_dying_players_own_empty_specialisation_is_not_counted_as_unknown() -> None:
    group = healers_of(card_for([], roster=(WARRIOR, GHOST), dying=GHOST))
    assert group.note == NO_OTHER_HEALER


def test_a_group_with_other_healers_and_an_unknown_specialisation_appends_a_sentence() -> None:
    group = healers_of(card_for([], roster=(DRUID, WARRIOR, UNKNOWN)))
    assert group.note.endswith(
        "The log names no specialisation for 1 other player, so a healer among them is not "
        "listed here."
    )


def test_the_group_is_badged_and_its_note_states_the_limits() -> None:
    hit = DamageTakenEvent(
        actor_id=WARRIOR.actor_id, ability_id=1, ability_name="Venom Bolt", amount=100,
        timestamp_ms=at(295),
    )
    group = healers_of(
        card_for([cast(DRUID, 20, None, ability_id=740)], damage_taken=(hit,))
    )
    assert group.badge is not None and group.badge.label == "measured"
    assert group.cooldown_badge is not None and group.cooldown_badge.label == "derived"
    assert group.note == (
        "Casts are counted where they were aimed, not by whom they healed: a smart heal or a "
        "heal over time can reach this player with no cast aimed at them, and a cast at an "
        "enemy can still heal, as Discipline's Atonement does. The heals that landed on this "
        "player are in this card's timeline, named by caster. A group healing cooldown reads as "
        "ready only when it was pressed somewhere in the log read for this run, not within its "
        "base cooldown before the damage began, and that base cooldown reaches back no further "
        "than the run's first second. Talents that shorten a cooldown are not modelled, a "
        "second charge reads as not ready, and a cooldown never pressed is not listed, so "
        "ready is understated, never invented. The log cannot show the healers' plan: a ready "
        "cooldown is a fact about the log, not a verdict on a healer."
    )


def test_an_untrimmed_card_with_an_empty_timeline_leaves_the_heals_sentence_out() -> None:
    group = healers_of(card_for([cast(DRUID, 20, None, ability_id=740)]))
    assert HEALER_AIM in group.note
    assert HEALER_LANDED not in group.note


def test_a_card_with_a_timeline_row_keeps_the_heals_sentence() -> None:
    hit = DamageTakenEvent(
        actor_id=WARRIOR.actor_id, ability_id=1, ability_name="Venom Bolt", amount=100,
        timestamp_ms=at(295),
    )
    group = healers_of(
        card_for([cast(DRUID, 20, None, ability_id=740)], damage_taken=(hit,))
    )
    assert HEALER_LANDED in group.note


def test_a_group_listing_no_cooldown_carries_no_derived_badge() -> None:
    group = healers_of(card_for([cast(DRUID, 295, None)]))
    assert group.cooldown_badge is None


def test_a_trimmed_card_does_not_point_at_a_timeline_it_does_not_draw() -> None:
    group = healers_of(card_for([], trimmed=True))
    assert HEALER_AIM in group.note
    assert HEALER_LANDED not in group.note


def test_no_sentence_says_on_cooldown_should_or_carries_a_healing_amount() -> None:
    casts = [cast(DRUID, 190, None, ability_id=740), cast(DRUID, 295, WARRIOR.actor_id)]
    group = healers_of(card_for(casts))
    texts = [group.note, *(line.summary for line in group.lines),
             *(line.note for line in group.lines),
             *(row.detail for line in group.lines for row in line.cooldowns)]
    for text in texts:
        assert "on cooldown" not in text, text
        assert "should" not in text, text
        assert not re.search(r"\d{1,3}(,\d{3})+|\d{4,}", text), text

# ABOUTME: The other healers' side of one death: who counts, where casts went, their cooldowns.
# ABOUTME: Every fixture sits on a clock whose origin is not zero, as report timestamps do.

from wowperf.domain.analysis.cooldown_reading import CooldownReading, Reading
from wowperf.domain.analysis.healer_side import TargetCounts, healer_side
from wowperf.domain.events import CastEvent, Death, Resurrection
from wowperf.domain.model import Player
from wowperf.domain.season import CooldownAbility, Roles, ThroughputCooldowns

ORIGIN = 3_000_000

DRUID = Player(actor_id=1, name="Emberkin", class_name="Druid", spec="Restoration", item_level=690)
PRIEST = Player(actor_id=2, name="Bríala", class_name="Priest", spec="Holy", item_level=690)
WARRIOR = Player(actor_id=3, name="Stonewake", class_name="Warrior", spec="Arms", item_level=690)
ROSTER = (DRUID, PRIEST, WARRIOR)
ENEMY = 900

TRANQUILITY = CooldownAbility(
    ability_id=740, name="Tranquility", cooldown_seconds=180.0, group=True
)
SWIFTNESS = CooldownAbility(ability_id=132158, name="Nature's Swiftness", cooldown_seconds=60.0)
HYMN = CooldownAbility(ability_id=64843, name="Divine Hymn", cooldown_seconds=180.0, group=True)
THROUGHPUT = ThroughputCooldowns(
    entries=(("Druid/Restoration", (TRANQUILITY, SWIFTNESS)), ("Priest/Holy", (HYMN,)))
)
ROLES = Roles(healers=("Druid/Restoration", "Priest/Holy"))

REJUVENATION = 774


def at(second: float) -> int:
    return ORIGIN + int(second * 1000)


def cast(player: Player, second: float, target: int | None, ability_id: int = REJUVENATION
         ) -> CastEvent:
    return CastEvent(
        actor_id=player.actor_id, ability_id=ability_id, ability_name="Rejuvenation",
        timestamp_ms=at(second), target_id=target,
    )


def death_of(player: Player, second: float) -> Death:
    return Death(player_name=player.name, actor_id=player.actor_id, timestamp_ms=at(second),
                 killing_blow="Venom Bolt")


def test_every_other_healer_counts_and_the_dying_healer_does_not() -> None:
    sides = healer_side(
        death_of(DRUID, 300), ROSTER, [], (), (), ROLES, THROUGHPUT, ORIGIN
    )
    assert [side.healer.name for side in sides] == ["Bríala"]


def test_a_group_with_no_other_healer_yields_no_side() -> None:
    only_druid = Roles(healers=("Druid/Restoration",))
    assert healer_side(
        death_of(DRUID, 300), ROSTER, [], (), (), only_druid, THROUGHPUT, ORIGIN
    ) == ()


def test_casts_in_the_run_up_are_counted_by_where_they_were_aimed() -> None:
    casts = [
        cast(DRUID, 291, WARRIOR.actor_id),
        cast(DRUID, 292, WARRIOR.actor_id),
        cast(DRUID, 293, DRUID.actor_id),
        cast(DRUID, 294, PRIEST.actor_id),
        cast(DRUID, 295, ENEMY),
        cast(DRUID, 296, None),
        cast(DRUID, 289, WARRIOR.actor_id),
    ]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.healer is DRUID
    assert side.casts == TargetCounts(
        at_player=2, at_self=1, at_other_players=1, at_non_players=1, untargeted=1
    )
    assert side.casts.total == 6


def test_the_last_cast_at_the_dying_player_is_the_latest_one_in_the_run_up() -> None:
    casts = [cast(DRUID, 292, WARRIOR.actor_id), cast(DRUID, 297, WARRIOR.actor_id),
             cast(DRUID, 299, PRIEST.actor_id)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.last_at_player_ms == at(297)


def test_no_cast_at_the_dying_player_leaves_no_last_cast() -> None:
    casts = [cast(DRUID, 285, WARRIOR.actor_id), cast(DRUID, 295, PRIEST.actor_id)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)[0]
    assert side.last_at_player_ms is None
    assert side.casts == TargetCounts(at_other_players=1)


def test_only_marked_cooldowns_are_read_and_a_never_pressed_one_is_left_out() -> None:
    casts = [cast(DRUID, 20, None, ability_id=740), cast(DRUID, 250, None, ability_id=132158)]
    side = healer_side(death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN)
    druid, priest = side
    assert [(one.ability.name, one.reading) for one in druid.cooldowns] == [
        ("Tranquility", CooldownReading(reading=Reading.READY))
    ]
    assert (druid.listed, priest.listed, priest.cooldowns) == (1, 1, ())


def test_a_cooldown_pressed_in_the_run_up_reads_pressed_whatever_its_target() -> None:
    casts = [cast(DRUID, 296, None, ability_id=740)]
    druid = healer_side(
        death_of(WARRIOR, 300), ROSTER, casts, (), (), ROLES, THROUGHPUT, ORIGIN
    )[0]
    assert druid.cooldowns[0].reading == CooldownReading(reading=Reading.PRESSED, press_ms=at(296))


def test_a_cooldown_is_judged_as_the_run_up_opens() -> None:
    pressed_just_inside_its_cooldown = cast(DRUID, 111, None, ability_id=740)
    druid = healer_side(
        death_of(WARRIOR, 300), ROSTER, [pressed_just_inside_its_cooldown], (), (), ROLES,
        THROUGHPUT, ORIGIN,
    )[0]
    assert druid.cooldowns[0].reading == CooldownReading(reading=Reading.WITHIN, press_ms=at(111))


def test_a_cast_at_a_dying_player_off_the_roster_counts_once() -> None:
    ghost_id = 99
    death = Death(player_name="Ghost", actor_id=ghost_id, timestamp_ms=at(300),
                  killing_blow="Venom Bolt")
    side = healer_side(
        death, ROSTER, [cast(DRUID, 295, ghost_id)], (), (), ROLES, THROUGHPUT, ORIGIN
    )[0]
    assert side.casts == TargetCounts(at_player=1)
    assert side.casts.total == 1


def test_a_dead_healer_is_dead_and_lists_no_cooldown() -> None:
    casts = [cast(DRUID, 20, None, ability_id=740), cast(DRUID, 292, WARRIOR.actor_id)]
    sides = healer_side(
        death_of(WARRIOR, 300), ROSTER, casts, (death_of(DRUID, 295),), (), ROLES, THROUGHPUT,
        ORIGIN,
    )
    druid = sides[0]
    assert (druid.dead, druid.cooldowns, druid.listed) == (True, (), 1)
    assert druid.casts == TargetCounts(at_player=1)


def test_a_healer_brought_back_before_the_death_is_alive() -> None:
    back = Resurrection(actor_id=DRUID.actor_id, caster_id=PRIEST.actor_id, ability_id=20484,
                        ability_name="Rebirth", timestamp_ms=at(295))
    sides = healer_side(
        death_of(WARRIOR, 300), ROSTER, [cast(DRUID, 20, None, ability_id=740)],
        (death_of(DRUID, 200),), (back,), ROLES, THROUGHPUT, ORIGIN,
    )
    assert sides[0].dead is False

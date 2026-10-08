# ABOUTME: Pairing the enemy-debuff stream into intervals: pets fold, targets key on game id.
# ABOUTME: Pins re-keying across two actor ids, end closure, orphans, re-applies and instances.

from wowperf.domain.debuffs import (
    DebuffEvent,
    DebuffInterval,
    DebuffLog,
    PairingTally,
    pair_debuffs,
)

PLAYER = 171
PET = 172
BLOOD_PLAGUE = 55078
WHELP = 189893
WHELP_ACTOR = 261
WHELP_TWIN = 263
FIGHT_END = 100_000


def an_event(
    applied: bool,
    at: int,
    *,
    source: int = PLAYER,
    source_instance: int = 0,
    target: int = WHELP_ACTOR,
    instance: int = 1,
) -> DebuffEvent:
    return DebuffEvent(
        applied=applied,
        timestamp_ms=at,
        source_id=source,
        source_instance=source_instance,
        target_id=target,
        target_instance=instance,
        ability_id=BLOOD_PLAGUE,
    )


def a_log(*events: DebuffEvent) -> DebuffLog:
    return DebuffLog(
        events=events,
        pet_owners=((PET, PLAYER),),
        game_ids=((WHELP_ACTOR, WHELP), (WHELP_TWIN, WHELP)),
        end_ms=FIGHT_END,
    )


def spans(intervals: tuple[DebuffInterval, ...]) -> list[tuple[int, int]]:
    return [(one.start_ms, one.end_ms) for one in intervals]


def test_an_apply_and_its_remove_make_one_interval_owned_by_the_caster() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(True, 1000), an_event(False, 4000)))

    assert intervals == (
        DebuffInterval(
            owner_id=PLAYER,
            ability_id=BLOOD_PLAGUE,
            target_game_id=WHELP,
            target_instance=1,
            start_ms=1000,
            end_ms=4000,
        ),
    )
    assert tally == PairingTally()


def test_a_pets_application_is_owned_by_its_owner() -> None:
    intervals, _ = pair_debuffs(
        a_log(
            an_event(True, 1000, source=PET, source_instance=2),
            an_event(False, 3000, source=PET, source_instance=2),
        )
    )

    assert [one.owner_id for one in intervals] == [PLAYER]


def test_one_enemy_logged_under_two_actor_ids_closes_its_own_interval() -> None:
    """Measured 2026-10-07 on a real key: 13 of one player's 168 applications
    opened on one actor id and closed on another of the same game id and copy
    number. Keyed on the actor id, every one of them would read as never removed.
    """
    intervals, tally = pair_debuffs(
        a_log(an_event(True, 1000, target=WHELP_ACTOR), an_event(False, 23_700, target=WHELP_TWIN))
    )

    assert spans(intervals) == [(1000, 23_700)]
    assert (tally.orphan_removes, tally.closed_at_end) == (0, 0)


def test_an_interval_still_open_is_closed_at_the_end_of_the_fight() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(True, 90_000)))

    assert spans(intervals) == [(90_000, FIGHT_END)]
    assert tally.closed_at_end == 1


def test_a_remove_with_no_open_application_is_counted_and_dropped() -> None:
    intervals, tally = pair_debuffs(a_log(an_event(False, 5000)))

    assert intervals == ()
    assert tally.orphan_removes == 1


def test_a_second_apply_while_open_keeps_the_first_start() -> None:
    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1000),
            an_event(True, 2000),
            an_event(False, 3000),
            an_event(False, 4000),
        )
    )

    assert spans(intervals) == [(1000, 3000)]
    assert tally.orphan_removes == 1


def test_two_copies_of_one_enemy_are_two_intervals() -> None:
    intervals, _ = pair_debuffs(
        a_log(
            an_event(True, 1000, instance=1),
            an_event(True, 1500, instance=2),
            an_event(False, 3000, instance=2),
            an_event(False, 4000, instance=1),
        )
    )

    assert sorted((one.target_instance, one.start_ms, one.end_ms) for one in intervals) == [
        (1, 1000, 4000),
        (2, 1500, 3000),
    ]


def test_a_pet_applying_and_removing_under_two_instances_closes_its_own_interval() -> None:
    """Measured 2026-10-08 on a cached key: every Mirror Image Frostbolt row came
    from one pet actor, applied under instance 25 and removed under instance 26.
    Keyed on the instance, all three removes were orphans and the first apply
    ran to the end of the fight. A remove shares its millisecond with the next
    apply, so the log's own order has to hold. The times are the trace's own
    gaps, started from one second.
    """
    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1_000, source=PET, source_instance=25),
            an_event(False, 8_400, source=PET, source_instance=26),
            an_event(True, 8_400, source=PET, source_instance=25),
            an_event(False, 9_850, source=PET, source_instance=26),
            an_event(True, 9_850, source=PET, source_instance=25),
            an_event(False, 16_920, source=PET, source_instance=26),
        )
    )

    assert spans(intervals) == [(1_000, 8_400), (8_400, 9_850), (9_850, 16_920)]
    assert [one.owner_id for one in intervals] == [PLAYER, PLAYER, PLAYER]
    assert tally == PairingTally()


def test_a_player_and_their_pet_are_two_keys_for_one_ability_on_one_target() -> None:
    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1000, source=PLAYER),
            an_event(True, 2000, source=PET, source_instance=2),
            an_event(False, 3000, source=PET, source_instance=2),
            an_event(False, 6000, source=PLAYER),
        )
    )

    assert sorted(spans(intervals)) == [(1000, 6000), (2000, 3000)]
    assert [one.owner_id for one in intervals] == [PLAYER, PLAYER]
    assert tally == PairingTally()


def test_two_players_applying_one_ability_to_one_target_do_not_close_each_other() -> None:
    other_player = 173

    intervals, tally = pair_debuffs(
        a_log(
            an_event(True, 1000, source=PLAYER),
            an_event(True, 2000, source=other_player),
            an_event(False, 3000, source=other_player),
            an_event(False, 6000, source=PLAYER),
        )
    )

    assert sorted((one.owner_id, one.start_ms, one.end_ms) for one in intervals) == [
        (PLAYER, 1000, 6000),
        (other_player, 2000, 3000),
    ]
    assert tally == PairingTally()


def test_a_target_with_no_game_id_is_counted_and_skipped() -> None:
    intervals, tally = pair_debuffs(
        a_log(an_event(True, 1000, target=999), an_event(False, 2000, target=999))
    )

    assert intervals == ()
    assert tally.unresolved_targets == 2

# ABOUTME: The data audit's rule: an entry never cast, and what the logs cast under its name.
# ABOUTME: Ids and names here are made up; the rule is about their relation, not any real spell.

from wowperf.domain.data_audit import AuditEntry, NeverCast, audit_lines, never_cast

SHIELD = AuditEntry(file="defensives", spec="Mage/Arcane", ability_id=100, name="Ice Shield")
BURST = AuditEntry(file="throughput_cooldowns", spec="Warrior/Arms", ability_id=300, name="Burst")


def test_an_entry_never_cast_whose_name_is_cast_under_another_id_is_reported() -> None:
    found = never_cast((SHIELD,), {200: 7}, {"ice shield": frozenset({100, 200})})
    assert found == (NeverCast(entry=SHIELD, cast_as=((200, 7),)),)


def test_an_entry_cast_under_its_own_id_is_not_reported() -> None:
    assert never_cast((SHIELD,), {100: 1, 200: 7}, {"ice shield": frozenset({100, 200})}) == ()


def test_an_id_a_table_names_but_no_row_casts_is_not_offered_as_the_replacement() -> None:
    found = never_cast((SHIELD,), {}, {"ice shield": frozenset({100, 200})})
    assert found == (NeverCast(entry=SHIELD, cast_as=()),)


def test_the_name_is_matched_whatever_its_case() -> None:
    found = never_cast((SHIELD,), {200: 1}, {"ice shield": frozenset({200})})
    assert found[0].cast_as == ((200, 1),)


def test_same_named_ids_come_most_cast_first_then_lowest_id() -> None:
    found = never_cast(
        (SHIELD,), {201: 3, 202: 9, 203: 3}, {"ice shield": frozenset({100, 201, 202, 203})}
    )
    assert found[0].cast_as == ((202, 9), (201, 3), (203, 3))


def test_the_lines_head_each_file_and_say_what_was_cast_instead() -> None:
    entries = (SHIELD, BURST)
    found = (NeverCast(entry=SHIELD, cast_as=((200, 7), (201, 2))), NeverCast(entry=BURST))
    assert audit_lines(entries, found) == (
        "defensives: 1 of 1 entries never cast",
        "  Mage/Arcane  Ice Shield  100: never cast; the logs cast it as 200 x7, 201 x2",
        "throughput_cooldowns: 1 of 1 entries never cast",
        "  Warrior/Arms  Burst  300: never cast, under this or any other id of that name",
    )


def test_a_file_with_nothing_never_cast_still_gets_its_heading() -> None:
    assert audit_lines((SHIELD,), ()) == ("defensives: 0 of 1 entries never cast",)

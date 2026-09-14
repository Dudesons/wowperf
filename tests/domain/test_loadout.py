# ABOUTME: Behaviour tests for the pure loadout values: items, stat ratings, and the tier rule.
# ABOUTME: The tier-slot rule is the one inference here, so it carries the most cases.

from wowperf.domain.loadout import TIER_SLOTS, EquippedItem, Loadout, StatBlock


def an_item(**changes: object) -> EquippedItem:
    fields: dict[str, object] = {
        "item_id": 271465,
        "slot": 0,
        "name": "Emberkin Helm",
        "item_level": 321,
        "enchant_id": 8017,
        "enchant_name": "Enchant Helm - Empowered Rune of Avoidance",
        "set_id": 2062,
    }
    fields.update(changes)
    return EquippedItem(**fields)  # type: ignore[arg-type]


def test_an_item_is_found_by_name() -> None:
    loadout = Loadout(items=(an_item(name="Stonewake Tablet"),))
    found = loadout.item_named("Stonewake Tablet")
    assert found is not None
    assert found.item_id == 271465


def test_a_name_that_is_not_equipped_finds_nothing() -> None:
    assert Loadout(items=(an_item(),)).item_named("Bríala's Pendant") is None


def test_an_item_is_found_by_id() -> None:
    assert Loadout(items=(an_item(item_id=99),)).has_item(99)
    assert not Loadout(items=(an_item(item_id=99),)).has_item(100)


def test_tier_pieces_counts_only_the_set_sitting_in_the_tier_slots() -> None:
    # Five items: three carry set 2062 in tier slots, two carry a different
    # set, 2070, outside them. The tier count is 3 -- the non-tier pair sits
    # outside {0, 2, 4, 6, 9} and adds nothing to it. This fixture alone does
    # not prove the slot filter runs (2070 only has two items here, so an
    # unfiltered count would still find 2062's three the largest); the case
    # where the outside set has MORE pieces than the tier set follows below.
    loadout = Loadout(
        items=(
            an_item(slot=0, set_id=2062),
            an_item(slot=2, set_id=2062),
            an_item(slot=4, set_id=2062),
            an_item(slot=12, set_id=2070),
            an_item(slot=15, set_id=2070),
        )
    )
    assert loadout.tier_pieces() == 3


def test_tier_pieces_ignores_a_larger_set_sitting_outside_the_tier_slots() -> None:
    # The mirror of design Section 2.6: set 2070 spans four classes in slots
    # 12 and 15 and is not tier. Here it out-numbers the true tier set 2062,
    # so a count that skips the slot filter would pick 2070's four pieces
    # instead of 2062's two, and return 4 rather than 2. Deleting the
    # `item.slot in TIER_SLOTS` check in `tier_pieces()` makes this go red.
    loadout = Loadout(
        items=(
            an_item(slot=0, set_id=2062),
            an_item(slot=2, set_id=2062),
            an_item(slot=12, set_id=2070),
            an_item(slot=13, set_id=2070),
            an_item(slot=15, set_id=2070),
            an_item(slot=16, set_id=2070),
        )
    )
    assert loadout.tier_pieces() == 2


def test_tier_pieces_is_zero_when_no_item_carries_a_set() -> None:
    assert Loadout(items=(an_item(slot=0, set_id=None),)).tier_pieces() == 0


def test_tier_pieces_picks_the_larger_set_when_two_sit_in_tier_slots() -> None:
    loadout = Loadout(
        items=(
            an_item(slot=0, set_id=2062),
            an_item(slot=2, set_id=2062),
            an_item(slot=4, set_id=2055),
        )
    )
    assert loadout.tier_pieces() == 2


def test_the_tier_slots_are_the_five_measured_ones() -> None:
    assert TIER_SLOTS == frozenset({0, 2, 4, 6, 9})


def test_enchanted_slots_lists_only_slots_carrying_an_enchant() -> None:
    loadout = Loadout(
        items=(
            an_item(slot=0, enchant_id=8017),
            an_item(slot=1, enchant_id=None),
            an_item(slot=2, enchant_id=0),
        )
    )
    assert loadout.enchanted_slots() == frozenset({0})


def test_occupied_slots_lists_every_slot_holding_an_item() -> None:
    loadout = Loadout(items=(an_item(slot=0), an_item(slot=7)))
    assert loadout.occupied_slots() == frozenset({0, 7})


def test_the_secondaries_are_the_four_a_player_gems_for_plus_the_three_tertiaries() -> None:
    stats = StatBlock(crit=904, haste=865, mastery=1196, versatility=0, leech=82, avoidance=226)
    assert stats.secondaries() == (
        ("crit", 904),
        ("haste", 865),
        ("mastery", 1196),
        ("versatility", 0),
        ("leech", 82),
        ("avoidance", 226),
        ("speed", 0),
    )


def test_the_total_secondary_rating_is_the_sum_of_them() -> None:
    stats = StatBlock(crit=100, haste=200, mastery=300, versatility=400)
    assert stats.total_secondary() == 1000


def test_a_loadout_has_no_stats_until_it_is_given_some() -> None:
    # Stats are None rather than a zeroed block: a player whose stats could not
    # be read must not compare as a player with none of every stat.
    assert Loadout().stats is None

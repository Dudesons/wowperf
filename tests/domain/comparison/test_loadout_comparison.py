# ABOUTME: Behaviour tests for the gear and stat comparison families.
# ABOUTME: item_sourced is asymmetric on purpose: a match is evidence, a miss is not.

from wowperf.domain.comparison.loadout import item_sourced, loadouts_of
from wowperf.domain.comparison.reference import ParseRow
from wowperf.domain.comparison.sample import ParseMember
from wowperf.domain.loadout import EquippedItem, Loadout
from wowperf.domain.model import Player, Run


def an_item(**changes: object) -> EquippedItem:
    fields: dict[str, object] = {
        "item_id": 250225,
        "slot": 12,
        "name": "Tablet of the Stonewake",
        "item_level": 331,
        "enchant_id": None,
        "enchant_name": None,
        "set_id": None,
    }
    fields.update(changes)
    return EquippedItem(**fields)  # type: ignore[arg-type]


def a_loadout(*items: EquippedItem) -> Loadout:
    return Loadout(items=items or (an_item(),))


def test_an_ability_named_after_an_equipped_item_resolves_to_it() -> None:
    # Measured 2026-09-14: Warcraft Logs names an on-use trinket's spell after
    # the item. Four of ten equipped trinkets matched the ability dictionary.
    found = item_sourced("Tablet of the Stonewake", [a_loadout()])
    assert found is not None
    assert found.item_id == 250225


def test_an_ability_matching_no_equipped_item_resolves_to_nothing() -> None:
    # A miss means unknown, never "this is a class spell". The measurement
    # shows a match indicates an item source; it does not show every
    # item-sourced ability matches by name.
    assert item_sourced("Arcane Blast", [a_loadout()]) is None


def test_any_loadout_in_the_sample_can_supply_the_match() -> None:
    others = [a_loadout(an_item(name="Bríala's Ember")), a_loadout(an_item(name="Ashen Coil"))]
    found = item_sourced("Ashen Coil", others)
    assert found is not None
    assert found.name == "Ashen Coil"


def test_no_loadouts_at_all_resolve_to_nothing() -> None:
    assert item_sourced("Ashen Coil", []) is None


def test_the_match_is_exact_rather_than_loose() -> None:
    # A substring rule would fold "Rune of Sanguination" into a rune consumable
    # and a "Tablet" into every tablet; the join is worth having only if it is
    # precise.
    assert item_sourced("Tablet", [a_loadout()]) is None
    assert item_sourced("tablet of the stonewake", [a_loadout()]) is None


# --- loadouts_of -------------------------------------------------------------


def a_reference_run(*players: Player) -> Run:
    return Run(
        report_code="REF1",
        fight_id=1,
        dungeon_name="Den of Stonewake",
        encounter_id=1,
        keystone_level=16,
        affix_ids=(),
        keystone_time_ms=1_000_000,
        keystone_bonus=1,
        count_reached=100,
        count_required=100,
        npc_counts=(),
        players=players,
        pulls=(),
    )


def a_reference_member(player: Player, *roster: Player) -> ParseMember:
    """A parse reference whose own report rosters `player` alongside `roster`."""
    return ParseMember(
        row=ParseRow(
            report_code="REF1",
            fight_id=1,
            keystone_level=16,
            duration_ms=1_000_000,
            character_name=player.name,
            class_name=player.class_name,
            spec=player.spec,
        ),
        run=a_reference_run(player, *roster),
    )


def test_loadouts_of_collects_each_members_own_players_loadout() -> None:
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout(an_item(name="Ashen Coil")))
    stonewake = Player(actor_id=12, name="Stonewake", class_name="Priest", spec="Shadow",
                        item_level=328, loadout=a_loadout(an_item(name="Bríala's Ember")))

    found = loadouts_of([a_reference_member(briala), a_reference_member(stonewake)])

    assert len(found) == 2
    assert {loadout.items[0].name for loadout in found} == {"Ashen Coil", "Bríala's Ember"}


def test_loadouts_of_skips_a_member_whose_loadout_was_never_fetched() -> None:
    # The speed axis, and every already-cached run, never fetch a loadout at
    # all -- `Player.loadout` stays None rather than an empty `Loadout`, and
    # that must not be mistaken for "equipped nothing".
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout())
    kirillica = Player(actor_id=13, name="Кириллица", class_name="Warrior", spec="Fury",
                        item_level=325)

    found = loadouts_of([a_reference_member(briala), a_reference_member(kirillica)])

    assert len(found) == 1
    assert found[0] is briala.loadout


def test_loadouts_of_skips_a_member_whose_player_cannot_be_found() -> None:
    # A row naming a character the report's own roster does not contain -- the
    # same gap `find_player` already has to handle -- contributes nothing
    # rather than raising.
    briala = Player(actor_id=11, name="Bríala", class_name="Mage", spec="Arcane",
                     item_level=330, loadout=a_loadout())
    ghost = ParseMember(
        row=ParseRow(
            report_code="REF2", fight_id=2, keystone_level=16, duration_ms=1_000_000,
            character_name="Nobody", class_name="Mage", spec="Arcane",
        ),
        run=a_reference_run(briala),
    )

    found = loadouts_of([ghost])

    assert found == ()

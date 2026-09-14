# ABOUTME: Behaviour tests for turning a playerDetails payload into loadouts by actor id.
# ABOUTME: The empty-combatantInfo case is the one a missing query argument produces.

from typing import Any

from wowperf.adapters.wcl.loadouts import build_loadouts


def a_payload(*players: dict[str, Any]) -> dict[str, Any]:
    return {
        "reportData": {
            "report": {
                "playerDetails": {"data": {"playerDetails": {"dps": list(players)}}}
            }
        }
    }


def a_player(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": 4,
        "name": "Emberkin",
        "type": "Mage",
        "combatantInfo": {
            "stats": {
                "Crit": {"min": 904, "max": 904},
                "Haste": {"min": 865, "max": 865},
                "Mastery": {"min": 1196, "max": 1196},
                "Versatility": {"min": 0, "max": 0},
                "Leech": {"min": 82, "max": 82},
                "Avoidance": {"min": 226, "max": 226},
                "Speed": {"min": 0, "max": 0},
                "Item Level": {"min": 320, "max": 320},
            },
            "gear": [
                {
                    "id": 271465,
                    "slot": 0,
                    "name": "Emberkin Helm",
                    "itemLevel": 321,
                    "permanentEnchant": 8017,
                    "permanentEnchantName": "Enchant Helm - Empowered Rune",
                    "setID": 2062,
                },
                {"id": 251234, "slot": 1, "name": "Stonewake Pendant", "itemLevel": 311},
            ],
        },
    }
    fields.update(changes)
    return fields


def test_a_player_becomes_a_loadout_keyed_by_actor_id() -> None:
    loadouts = build_loadouts(a_payload(a_player()))
    assert set(loadouts) == {4}


def test_the_stat_ratings_are_read_from_min() -> None:
    stats = build_loadouts(a_payload(a_player()))[4].stats
    assert stats is not None
    assert (stats.crit, stats.haste, stats.mastery) == (904, 865, 1196)


def test_item_level_is_not_a_secondary_stat() -> None:
    # "Item Level" sits in the same block and is not a rating; leaking it into
    # a stat field would put a 320 beside a 904 as though they were comparable.
    stats = build_loadouts(a_payload(a_player()))[4].stats
    assert stats is not None
    assert stats.total_secondary() == 904 + 865 + 1196 + 0 + 82 + 226 + 0


def test_gear_is_read_with_its_enchant_and_set() -> None:
    items = build_loadouts(a_payload(a_player()))[4].items
    assert len(items) == 2
    helm = items[0]
    assert (helm.item_id, helm.slot, helm.item_level) == (271465, 0, 321)
    assert helm.enchant_id == 8017
    assert helm.set_id == 2062


def test_an_item_with_no_enchant_or_set_reads_as_having_neither() -> None:
    pendant = build_loadouts(a_payload(a_player()))[4].items[1]
    assert pendant.enchant_id is None
    assert pendant.set_id is None


def test_an_empty_combatant_info_yields_no_loadout_at_all() -> None:
    # This is exactly what a query missing `includeCombatantInfo: true` returns.
    # It must not read as a player who equipped nothing.
    assert build_loadouts(a_payload(a_player(combatantInfo=[]))) == {}


def test_a_missing_combatant_info_yields_no_loadout() -> None:
    assert build_loadouts(a_payload(a_player(combatantInfo=None))) == {}


def test_stats_are_withheld_when_a_rating_moved_during_the_fight() -> None:
    # min equalled max for every stat of every player measured on 2026-09-14.
    # A divergence means the reading is not a single number, and guessing which
    # end to take would be a modelling choice nothing here can justify.
    player = a_player()
    player["combatantInfo"]["stats"]["Crit"] = {"min": 900, "max": 1100}
    loadout = build_loadouts(a_payload(player))[4]
    assert loadout.stats is None
    assert len(loadout.items) == 2


def test_a_stat_absent_from_the_block_reads_as_zero() -> None:
    player = a_player()
    del player["combatantInfo"]["stats"]["Leech"]
    stats = build_loadouts(a_payload(player))[4].stats
    assert stats is not None
    assert stats.leech == 0


def test_every_role_group_is_read() -> None:
    payload = {
        "reportData": {
            "report": {
                "playerDetails": {
                    "data": {
                        "playerDetails": {
                            "tanks": [a_player(id=1)],
                            "healers": [a_player(id=2)],
                            "dps": [a_player(id=3)],
                        }
                    }
                }
            }
        }
    }
    assert set(build_loadouts(payload)) == {1, 2, 3}


def test_a_payload_with_no_player_details_yields_nothing() -> None:
    assert build_loadouts({"reportData": {"report": {}}}) == {}

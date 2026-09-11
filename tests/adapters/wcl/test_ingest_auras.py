# ABOUTME: Turns the aliased aura table into domain values, with real payload shapes.
# ABOUTME: Fixtures follow the schema verified against the live API on 2026-09-05.

from typing import Any

import pytest

from wowperf.adapters.wcl.ingest import IngestError, build_player_auras


def a_table(*auras: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"auras": list(auras), "totalTime": 1857623}}


def an_aura(name: str, guid: int, *bands: tuple[int, int]) -> dict[str, Any]:
    return {
        "name": name,
        "guid": guid,
        "type": 1,
        "abilityIcon": "spell_holy_symbolofhope.jpg",
        "totalUptime": sum(end - start for start, end in bands),
        "totalUses": len(bands),
        "bands": [{"startTime": start, "endTime": end} for start, end in bands],
    }


def a_payload(on_self: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"onSelf": on_self}}}


def test_the_buff_table_lands_as_what_the_player_carried() -> None:
    payload = a_payload(a_table(an_aura("Coagulopathy", 391477, (0, 5000))))

    auras = build_player_auras(payload, actor_id=7)

    assert auras.actor_id == 7
    assert [a.name for a in auras.on_self] == ["Coagulopathy"]


def test_the_wire_calls_it_guid_and_the_domain_calls_it_an_ability_id() -> None:
    payload = a_payload(a_table(an_aura("Coagulopathy", 391477, (0, 5000))))

    assert build_player_auras(payload, actor_id=7).on_self[0].ability_id == 391477


def test_bands_survive_with_their_timestamps() -> None:
    payload = a_payload(a_table(an_aura("Voracious", 274009, (100, 400), (900, 1000))))

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert [(b.start_ms, b.end_ms) for b in aura.bands] == [(100, 400), (900, 1000)]
    assert aura.total_uptime_ms == 400
    assert aura.uses == 2


def test_an_aura_with_no_bands_is_kept_rather_than_dropped() -> None:
    bandless = {"name": "Satiated", "guid": 326809, "totalUptime": 0, "totalUses": 1}
    payload = a_payload(a_table(bandless))

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert aura.bands == ()
    assert aura.uses == 1


def test_an_empty_table_yields_no_auras_rather_than_raising() -> None:
    payload = a_payload({"data": {"auras": [], "totalTime": 0}})

    assert build_player_auras(payload, actor_id=7).on_self == ()


def test_a_missing_table_block_is_an_error_not_an_empty_result() -> None:
    payload = {"reportData": {"report": {"onSelf": None}}}

    with pytest.raises(IngestError, match="onSelf"):
        build_player_auras(payload, actor_id=7)


def test_the_aura_table_query_asks_only_for_the_players_own_buffs() -> None:
    """The enemy-debuff table cannot be scoped to one caster, so asking for it
    would pay for a selection whose every row belongs to the whole group. See the
    wcl-api skill, "The debuff half cannot be scoped to one caster"."""
    from wowperf.adapters.wcl.queries import AURA_TABLE_QUERY

    assert "Buffs" in AURA_TABLE_QUERY
    assert "Debuffs" not in AURA_TABLE_QUERY


def test_the_aura_table_query_allows_unlisted_reports() -> None:
    from wowperf.adapters.wcl.queries import AURA_TABLE_QUERY

    assert "allowUnlisted: true" in AURA_TABLE_QUERY

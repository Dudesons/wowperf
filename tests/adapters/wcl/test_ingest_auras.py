# ABOUTME: Turns the two aliased aura tables into domain values, with real payload shapes.
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


def a_payload(on_self: dict[str, Any], on_targets: dict[str, Any]) -> dict[str, Any]:
    return {"reportData": {"report": {"onSelf": on_self, "onTargets": on_targets}}}


def test_both_halves_land_on_the_side_they_came_from() -> None:
    payload = a_payload(
        a_table(an_aura("Coagulopathy", 391477, (0, 5000))),
        a_table(an_aura("Frost Fever", 55095, (1000, 2000))),
    )

    auras = build_player_auras(payload, actor_id=7)

    assert auras.actor_id == 7
    assert [a.name for a in auras.on_self] == ["Coagulopathy"]
    assert [a.name for a in auras.on_targets] == ["Frost Fever"]


def test_the_wire_calls_it_guid_and_the_domain_calls_it_an_ability_id() -> None:
    payload = a_payload(a_table(an_aura("Coagulopathy", 391477, (0, 5000))), a_table())

    assert build_player_auras(payload, actor_id=7).on_self[0].ability_id == 391477


def test_bands_survive_with_their_timestamps() -> None:
    payload = a_payload(a_table(an_aura("Voracious", 274009, (100, 400), (900, 1000))), a_table())

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert [(b.start_ms, b.end_ms) for b in aura.bands] == [(100, 400), (900, 1000)]
    assert aura.total_uptime_ms == 400
    assert aura.uses == 2


def test_an_aura_with_no_bands_is_kept_rather_than_dropped() -> None:
    bandless = {"name": "Satiated", "guid": 326809, "totalUptime": 0, "totalUses": 1}
    payload = a_payload(a_table(bandless), a_table())

    aura = build_player_auras(payload, actor_id=7).on_self[0]

    assert aura.bands == ()
    assert aura.uses == 1


def test_an_empty_table_yields_no_auras_rather_than_raising() -> None:
    payload = a_payload({"data": {"auras": [], "totalTime": 0}}, a_table())

    assert build_player_auras(payload, actor_id=7).on_self == ()


def test_a_missing_table_block_is_an_error_not_an_empty_result() -> None:
    payload = {"reportData": {"report": {"onSelf": None, "onTargets": None}}}

    with pytest.raises(IngestError, match="onSelf"):
        build_player_auras(payload, actor_id=7)


def test_the_aura_table_query_allows_unlisted_reports() -> None:
    from wowperf.adapters.wcl.queries import AURA_TABLE_QUERY

    assert "allowUnlisted: true" in AURA_TABLE_QUERY

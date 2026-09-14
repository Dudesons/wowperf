# ABOUTME: Maps a viewBy-Ability damage-taken table into rows the comparison reads.
# ABOUTME: Landings are hits plus ticks; misses are counted and never added to them.

import pytest

from wowperf.adapters.wcl.ability_tables import build_ability_taken_rows
from wowperf.adapters.wcl.errors import WclError


def payload(entries: list[dict[str, object]]) -> dict[str, object]:
    return {"reportData": {"report": {"taken": {"data": {"entries": entries}}}}}


def test_landings_are_hits_plus_ticks_and_exclude_misses() -> None:
    rows = build_ability_taken_rows(
        payload(
            [
                {
                    "guid": 400,
                    "name": "Ravenous Feast",
                    "hitCount": 7,
                    "tickCount": 5,
                    "missCount": 3,
                    "tickMissCount": 2,
                    "sources": [{"name": "The Twin Fangs", "type": "Boss"}],
                }
            ]
        ),
        "taken",
    )
    assert len(rows) == 1
    # 7 + 5 = 12. The two miss counts total 5 and must not reach it.
    assert rows[0].landings == 12
    assert rows[0].miss_count == 3
    assert rows[0].tick_miss_count == 2


def test_a_missing_count_field_reads_zero_rather_than_raising() -> None:
    # Rows carrying only some of the four counts were observed on real fights.
    rows = build_ability_taken_rows(
        payload([{"guid": 401, "name": "Coiling Ichor", "tickCount": 4, "sources": []}]),
        "taken",
    )
    assert rows[0].landings == 4
    assert rows[0].hit_count == 0
    assert rows[0].source_types == ()


def test_source_types_are_carried_verbatim_for_the_domain_to_judge() -> None:
    rows = build_ability_taken_rows(
        payload(
            [
                {
                    "guid": 6940,
                    "name": "Blessing of Sacrifice",
                    "hitCount": 2,
                    "sources": [{"name": "Stonewake", "type": "Warrior"}],
                }
            ]
        ),
        "taken",
    )
    # The adapter maps and decides nothing: whether a Warrior-sourced row is a
    # mechanic is the domain's judgement, in mechanics.py.
    assert rows[0].source_types == ("Warrior",)


def test_an_absent_selection_raises_naming_the_alias() -> None:
    # No `taken` key at all -- the alias the caller asked for was never in
    # the response, distinct from having been asked for and coming back null.
    with pytest.raises(WclError, match="`taken`"):
        build_ability_taken_rows({"reportData": {"report": {}}}, "taken")


def test_a_null_selection_raises_the_same_as_an_absent_one() -> None:
    # A selection that failed server-side comes back as `null`, not as a
    # missing key. Reading past it silently would report "no damage taken"
    # for a fight the query never actually asked about successfully.
    with pytest.raises(WclError, match="`taken`"):
        build_ability_taken_rows({"reportData": {"report": {"taken": None}}}, "taken")

# ABOUTME: Turns a report's own `rankings` payload into `ReportRankings` domain values.
# ABOUTME: A wipe's empty row list becomes `None`, never a zeroed row.

from typing import Any

from wowperf.adapters.wcl.report_rankings import build_report_rankings

PAYLOAD: dict[str, Any] = {
    "reportData": {
        "report": {
            "rankings": {
                "data": [
                    {
                        "fightID": 2,
                        "difficulty": 4,
                        "partition": 1,
                        "size": 20,
                        "kill": True,
                        "roles": {
                            "tanks": {"characters": [
                                {"name": "Stonewake", "class": "Warrior", "spec": "Protection",
                                 "amount": 44818.47826087, "rank": "~3747", "best": "~2017",
                                 "rankPercent": 87, "bracketPercent": 81, "totalParses": 28826},
                            ]},
                            "healers": {"characters": []},
                            "dps": {"characters": [
                                {"name": "Emberkin", "class": "Evoker", "spec": "Devastation",
                                 "amount": 247358.15773571, "rank": "~12", "best": "~9",
                                 "rankPercent": 96, "bracketPercent": 94, "totalParses": 31004},
                            ]},
                        },
                    }
                ]
            }
        }
    }
}


def test_a_rankings_row_becomes_one_ranked_player_per_role() -> None:
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    assert built.difficulty == 4
    assert built.partition == 1
    assert built.size == 20
    assert built.kill is True
    assert len(built.players) == 2
    assert {player.role for player in built.players} == {"tanks", "dps"}


def test_a_rank_survives_the_tilde_the_api_puts_on_it() -> None:
    """`rank` and `best` are strings. Measured 2026-09-14: they read "~5764"."""
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    [tank] = built.rows_named("Stonewake")
    assert tank.rank == "~3747"
    assert tank.best == "~2017"
    assert tank.rank_percent == 87
    assert tank.bracket_percent == 81


def test_the_two_players_differ_in_every_field_a_finding_reads() -> None:
    """Guard against an identity fixture: two rows that agree test nothing."""
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    [tank] = built.rows_named("Stonewake")
    [dps] = built.rows_named("Emberkin")
    assert tank.amount != dps.amount
    assert tank.rank != dps.rank
    assert tank.rank_percent != dps.rank_percent
    assert tank.bracket_percent != dps.bracket_percent
    assert tank.total_parses != dps.total_parses
    assert tank.role != dps.role


def test_a_wipe_returns_no_row_and_the_builder_says_so_rather_than_inventing_one() -> None:
    """Design section 14 item 7: a wipe returns an empty list, with no field
    distinguishing it from a kill. Code tests for emptiness."""
    empty: dict[str, Any] = {"reportData": {"report": {"rankings": {"data": []}}}}
    assert build_report_rankings(empty, fight_id=2) is None


def test_a_row_for_another_fight_is_not_mistaken_for_ours() -> None:
    other: dict[str, Any] = {"reportData": {"report": {"rankings": {"data": [
        {**PAYLOAD["reportData"]["report"]["rankings"]["data"][0], "fightID": 30}
    ]}}}}
    assert build_report_rankings(other, fight_id=2) is None


def test_a_name_matches_whatever_case_the_roster_spells_it_in() -> None:
    built = build_report_rankings(PAYLOAD, fight_id=2)
    assert built is not None
    assert len(built.rows_named("stonewake")) == 1
    assert len(built.rows_named("STONEWAKE")) == 1
    assert built.rows_named("Bríala") == ()

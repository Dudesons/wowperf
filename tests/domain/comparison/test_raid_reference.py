# ABOUTME: Behaviour tests for ReportRankings.player_named, the one behaviour this module holds.
# ABOUTME: Everything else in raid_reference.py is data, carrying nothing worth asserting alone.

from wowperf.domain.comparison.raid_reference import RankedPlayer, ReportRankings


def a_ranked_player(name: str, role: str) -> RankedPlayer:
    return RankedPlayer(
        character_name=name,
        class_name="Warrior",
        spec="Protection",
        role=role,
        amount=1.0,
        rank="~1",
        best="~1",
        rank_percent=1,
        bracket_percent=1,
        total_parses=1,
    )


def a_report_rankings() -> ReportRankings:
    return ReportRankings(
        fight_id=2,
        difficulty=4,
        partition=1,
        size=20,
        kill=True,
        players=(a_ranked_player("Stonewake", "tanks"), a_ranked_player("Emberkin", "dps")),
    )


def test_a_name_matches_whatever_case_the_caller_spells_it_in() -> None:
    rankings = a_report_rankings()
    assert rankings.player_named("stonewake") is rankings.players[0]
    assert rankings.player_named("STONEWAKE") is rankings.players[0]


def test_an_absent_name_returns_none() -> None:
    assert a_report_rankings().player_named("Bríala") is None


def test_two_players_are_told_apart_rather_than_the_first_answering_for_any_query() -> None:
    """Guards against a `player_named` that ignores its argument and returns
    `self.players[0]` for every query."""
    rankings = a_report_rankings()
    stonewake = rankings.player_named("Stonewake")
    emberkin = rankings.player_named("Emberkin")
    assert stonewake is not None and stonewake.character_name == "Stonewake"
    assert emberkin is not None and emberkin.character_name == "Emberkin"

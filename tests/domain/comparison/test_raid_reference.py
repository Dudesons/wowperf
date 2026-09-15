# ABOUTME: Behaviour tests for ReportRankings.rows_named, the one behaviour this module holds.
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
    assert rankings.rows_named("stonewake") == (rankings.players[0],)
    assert rankings.rows_named("STONEWAKE") == (rankings.players[0],)


def test_an_absent_name_returns_no_rows() -> None:
    assert a_report_rankings().rows_named("Bríala") == ()


def test_two_players_are_told_apart_rather_than_the_first_answering_for_any_query() -> None:
    """Guards against a `rows_named` that ignores its argument and returns
    `self.players` for every query."""
    rankings = a_report_rankings()
    [stonewake] = rankings.rows_named("Stonewake")
    [emberkin] = rankings.rows_named("Emberkin")
    assert stonewake.character_name == "Stonewake"
    assert emberkin.character_name == "Emberkin"


def test_a_name_two_rows_carry_answers_with_both_rather_than_with_the_first() -> None:
    """The count is the whole point of the tuple.

    A rankings row carries no actor id, so two roster members of one name are
    two rows this report cannot separate -- and a lookup answering with the
    first hands the second player the first one's standing. Returning both is
    what lets a caller see the ambiguity and refuse to guess.
    """
    rankings = ReportRankings(
        fight_id=2,
        difficulty=4,
        partition=1,
        size=20,
        kill=True,
        players=(a_ranked_player("Emberkin", "dps"), a_ranked_player("Emberkin", "tanks")),
    )

    found = rankings.rows_named("Emberkin")

    assert found == rankings.players
    assert [row.role for row in found] == ["dps", "tanks"]

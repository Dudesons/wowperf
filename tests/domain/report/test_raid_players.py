# ABOUTME: Behaviour tests for the raid Players tab -- one card per raider.
# ABOUTME: A row reaches a card by the slug it carries, never by who the subject is.

from tests.domain.report.test_raid_frame import an_encounter
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player
from wowperf.domain.report.frame import NOT_REQUESTED
from wowperf.domain.report.model import LedgerRow, PlayerCard, SectionState
from wowperf.domain.report.raid_players import build_raid_players


def a_finding(
    finding_id: str,
    title: str = "x",
    detail: str = "detail",
    slug: str = "",
) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail=detail,
        confidence=Confidence.DERIVED,
        player_slug=slug,
    )


def a_player(actor_id: int, name: str, class_name: str = "Druid", spec: str = "Balance") -> Player:
    return Player(actor_id=actor_id, name=name, class_name=class_name, spec=spec, item_level=680)


def a_loaded(players: tuple[Player, ...]) -> LoadedEncounter:
    return LoadedEncounter(encounter=an_encounter(players=players))


def comparison_rows(card: PlayerCard) -> tuple[LedgerRow, ...]:
    return card.spell_and_talent_rows


def two_compared_raiders() -> tuple[
    LoadedEncounter, tuple[Finding, ...], Player, frozenset[str], dict[str, str]
]:
    emberkin = a_player(1, "Emberkin")
    stonewake = a_player(2, "Stonewake", class_name="DeathKnight", spec="Blood")
    loaded = a_loaded(players=(emberkin, stonewake))
    findings = (
        a_finding(
            "compare.spells.missing.0.emberkin-0",
            title="Missing Frost Nova",
            slug="emberkin-0",
        ),
        a_finding(
            "compare.spells.missing.0.stonewake-1",
            title="Missing Death Grip",
            slug="stonewake-1",
        ),
    )
    return loaded, findings, emberkin, frozenset({"emberkin-0", "stonewake-1"}), {}


def one_compared_one_not() -> tuple[
    LoadedEncounter, tuple[Finding, ...], Player, frozenset[str], dict[str, str]
]:
    # The compared raider is also the roster's own first entry, so it lands
    # first in the returned cards whichever ordering rule the builder uses --
    # the point of this fixture is the three comparison states, not the order.
    emberkin = a_player(1, "Emberkin")
    stonewake = a_player(2, "Stonewake", class_name="DeathKnight", spec="Blood")
    loaded = a_loaded(players=(emberkin, stonewake))
    findings = (
        a_finding(
            "compare.spells.missing.0.emberkin-0",
            title="Missing Frost Nova",
            slug="emberkin-0",
        ),
    )
    return loaded, findings, emberkin, frozenset({"emberkin-0"}), {}


def a_wiped_attempt() -> tuple[
    LoadedEncounter, tuple[Finding, ...], Player, frozenset[str], dict[str, str]
]:
    emberkin = a_player(1, "Emberkin")
    stonewake = a_player(2, "Stonewake", class_name="DeathKnight", spec="Blood")
    loaded = a_loaded(players=(emberkin, stonewake))
    findings = (
        a_finding(
            "compare.parse.unavailable.emberkin-0",
            title="No rankings for a wipe",
            detail="Warcraft Logs computes no rankings row for an attempt that did not kill.",
            slug="emberkin-0",
        ),
        a_finding(
            "compare.parse.unavailable.stonewake-1",
            title="No rankings for a wipe",
            detail="Warcraft Logs computes no rankings row for an attempt that did not kill.",
            slug="stonewake-1",
        ),
    )
    return loaded, findings, emberkin, frozenset({"emberkin-0", "stonewake-1"}), {}


def a_roster_where_the_subject_is_not_first() -> tuple[
    LoadedEncounter, tuple[Finding, ...], Player, frozenset[str] | None, dict[str, str]
]:
    # Three raiders so "subject first" and "roster order" print different
    # sequences -- a subject who already sits at index 0 cannot tell the two
    # rules apart. Bríala is last on the roster and is the subject.
    emberkin = a_player(1, "Emberkin")
    stonewake = a_player(2, "Stonewake", class_name="DeathKnight", spec="Blood")
    briala = a_player(3, "Bríala", class_name="Priest", spec="Discipline")
    loaded = a_loaded(players=(emberkin, stonewake, briala))
    return loaded, (), briala, None, {}


def test_a_raiders_rows_land_on_their_own_card() -> None:
    """Routed by the slug the finding carries, never by who the subject is.

    A raid compares twenty people at once, so routing to the subject's card
    would put nineteen raiders' rows under one name.
    """
    cards = build_raid_players(*two_compared_raiders())

    by_slug = {card.slug: card for card in cards}
    assert set(by_slug) == {"emberkin-0", "stonewake-1"}
    for slug, card in by_slug.items():
        ids = [row.finding_id for row in comparison_rows(card)]
        assert ids, f"{slug} drew no comparison rows at all"
        assert all(finding_id.endswith(f".{slug}") for finding_id in ids), ids


def test_the_card_nobody_asked_for_says_so_rather_than_looking_clean() -> None:
    """Three states, and the difference between them is the whole point.

    A raider nobody named, a raider whose leaderboard offered nothing, and a
    raider compared and found level are three different pages. Silence reads
    as the third.
    """
    cards = build_raid_players(*one_compared_one_not())

    asked, not_asked = cards[0], cards[1]
    assert NOT_REQUESTED in not_asked.spell_and_talent.reason
    assert not_asked.spell_and_talent.state is SectionState.WITHHELD
    assert asked.spell_and_talent.state is SectionState.PRESENT


def test_a_wipe_tells_every_raider_why_their_comparison_is_empty() -> None:
    """Design section 13: an empty section teaches nothing.

    Warcraft Logs computes no rankings row for an attempt that did not kill,
    so the external frame is withheld for everybody -- and the page has to say
    that, in words, on each card.
    """
    cards = build_raid_players(*a_wiped_attempt())

    assert cards, "the fixture built no cards"
    for card in cards:
        ids = [row.finding_id for row in comparison_rows(card)]
        assert any(
            finding_id.startswith("compare.parse.unavailable") for finding_id in ids
        ), card.slug


def test_the_subjects_card_opens_first_whatever_the_rosters_own_order() -> None:
    """The Players tab opens whichever card is drawn first.

    A subject who is not the roster's first entry is the only fixture that
    can tell "subject first" apart from "roster order" -- either rule prints
    the same sequence when the subject already sits at index 0. Get this
    wrong and `--player` names one raider while the tab that opens is
    someone else's.
    """
    cards = build_raid_players(*a_roster_where_the_subject_is_not_first())

    assert cards, "the fixture built no cards"
    assert [card.name for card in cards] == ["Bríala", "Emberkin", "Stonewake"]

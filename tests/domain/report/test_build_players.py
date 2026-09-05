# ABOUTME: Behaviour tests for the interrupts section and the per-player cards.
# ABOUTME: No card claims damage was avoidable — the log does not record that, and neither do we.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_interrupts, build_players, class_colour
from wowperf.domain.report.model import LedgerRow, SectionState


def a_finding(finding_id: str, seconds: float | None = None, title: str = "x") -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail="detail",
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


def a_player(actor_id: int = 1, name: str = "Dudesons") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_loaded() -> LoadedRun:
    return LoadedRun(run=a_run(players=(a_player(),), pulls=(a_pull(0, 0, 120_000),)))


def ids(rows: tuple[LedgerRow, ...]) -> list[str]:
    return [row.finding_id for row in rows]


def test_the_interrupts_section_takes_its_findings() -> None:
    rows = build_interrupts((a_finding("interrupts.summary"), a_finding("interrupts.ability.0")))
    assert ids(rows) == ["interrupts.summary", "interrupts.ability.0"]


def test_the_interrupts_section_leaves_timed_findings_to_the_ledger() -> None:
    rows = build_interrupts((a_finding("compare.interrupts", seconds=40.0),))
    assert ids(rows) == []


def test_the_interrupts_section_takes_nothing_that_is_not_an_interrupt() -> None:
    rows = build_interrupts((a_finding("players.damage.0"),))
    assert ids(rows) == []


def test_one_card_per_player() -> None:
    cards = build_players(a_loaded(), (), None)
    assert [card.name for card in cards] == ["Dudesons"]


def test_a_card_names_the_class_in_text_beside_its_colour() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert card.class_name == "DeathKnight"
    assert card.colour == class_colour("DeathKnight")
    assert card.colour != card.class_name


def test_an_unknown_class_still_gets_a_colour_rather_than_an_empty_string() -> None:
    assert class_colour("Bard") == "class-unknown"


def test_a_card_carries_its_players_damage_findings() -> None:
    findings = (a_finding("players.damage.0", title="Dudesons took 2.3x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert ids(card.damage_rows) == ["players.damage.0"]


def test_a_card_never_calls_damage_avoidable() -> None:
    findings = (a_finding("players.damage.0", title="Dudesons took 2.3x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert "avoidable" not in " ".join(row.title + row.detail for row in card.damage_rows).lower()


def test_a_card_only_takes_damage_findings_naming_that_player() -> None:
    findings = (a_finding("players.damage.0", title="Someoneelse took 4.1x the group median"),)
    card = build_players(a_loaded(), findings, None)[0]
    assert ids(card.damage_rows) == []


def test_without_a_parse_reference_the_comparison_half_is_withheld() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert card.spell_and_talent.state is SectionState.WITHHELD
    assert card.spell_and_talent.reason
    assert card.spell_and_talent_rows == ()


def test_a_card_states_active_time_as_a_share_of_pull_time() -> None:
    card = build_players(a_loaded(), (), None)[0]
    assert "%" in card.active_time

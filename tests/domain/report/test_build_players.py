# ABOUTME: Behaviour tests for the interrupts section and the per-player cards.
# ABOUTME: A card carries a finding's title and detail unchanged; it adds no framing of its own.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.comparison.reference import ParseReference, ParseRow
from wowperf.domain.events import CastEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.build import build_players, class_colour, place_rows
from wowperf.domain.report.model import LedgerRow, SectionState


def a_finding(
    finding_id: str, seconds: float | None = None, title: str = "x", detail: str = "detail"
) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail=detail,
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
    )


def titles(findings: tuple[Finding, ...]) -> dict[str, str]:
    return {finding.id: finding.title for finding in findings}


def a_player(actor_id: int = 1, name: str = "Dudesons") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_loaded(players: tuple[Player, ...] | None = None) -> LoadedRun:
    return LoadedRun(
        run=a_run(players=players or (a_player(),), pulls=(a_pull(0, 0, 120_000),))
    )


def a_parse(character_name: str = "SomeoneElsesTopParse") -> ParseReference:
    return ParseReference(
        row=ParseRow(
            report_code="def456",
            fight_id=12,
            keystone_level=16,
            duration_ms=1_000_000,
            character_name=character_name,
            class_name="DeathKnight",
            spec="Blood",
        ),
        loaded=a_loaded(),
    )


def ids(rows: tuple[LedgerRow, ...]) -> list[str]:
    return [row.finding_id for row in rows]


def test_the_interrupts_section_takes_its_findings() -> None:
    findings = (a_finding("interrupts.summary"), a_finding("interrupts.ability.0"))
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == ["interrupts.summary", "interrupts.ability.0"]


def test_a_timed_interrupt_finding_lands_in_interrupts_too() -> None:
    # PLACEMENTS now sends every "compare.interrupts" row to the Interrupts tab,
    # timed or not: there is no page-wide ledger of losses left for it to go to instead.
    findings = (a_finding("compare.interrupts", seconds=40.0),)
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == ["compare.interrupts"]


def test_the_interrupts_section_takes_nothing_that_is_not_an_interrupt() -> None:
    findings = (a_finding("players.damage.0"),)
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == []


def test_one_card_per_player() -> None:
    cards = build_players(a_loaded(), (), None, a_player(), {})
    assert [card.name for card in cards] == ["Dudesons"]


def test_two_players_sharing_a_name_get_disambiguated_card_names() -> None:
    # Two visually identical cards for two different people is exactly what a
    # shared display name must not produce; the actor id disambiguates both,
    # the same way `display_names` disambiguates the finding titles that name them.
    loaded = a_loaded(players=(a_player(1, "Sublime"), a_player(5, "Sublime")))
    cards = build_players(loaded, (), None, a_player(1, "Sublime"), {})
    assert [card.name for card in cards] == ["Sublime (actor 1)", "Sublime (actor 5)"]


def test_a_card_names_the_class_in_text_beside_its_colour() -> None:
    card = build_players(a_loaded(), (), None, a_player(), {})[0]
    assert card.class_name == "DeathKnight"
    assert card.colour == class_colour("DeathKnight")
    assert card.colour != card.class_name


def test_an_unknown_class_still_gets_a_colour_rather_than_an_empty_string() -> None:
    assert class_colour("Bard") == "class-unknown"


def test_a_card_carries_its_players_damage_findings() -> None:
    findings = (a_finding("players.damage.0", title="Dudesons took 2.3x the group median"),)
    card = build_players(a_loaded(), findings, None, a_player(), titles(findings))[0]
    assert ids(card.damage_rows) == ["players.damage.0"]


def test_a_damage_rows_title_and_detail_are_the_findings_own_unchanged() -> None:
    """The card is a pass-through: the analyser's own avoidable-damage disclaimer,
    which uses the word "avoidable" in order to deny it applies, survives verbatim.
    """
    detail = (
        "184320 unmitigated damage from Rending Slash. This states a difference, "
        "not a mistake: whether any single hit was avoidable is not something "
        "the log records."
    )
    finding = a_finding(
        "players.damage.0",
        title="Dudesons took 2.3x the group median from Rending Slash",
        detail=detail,
    )
    findings = (finding,)
    card = build_players(a_loaded(), findings, None, a_player(), titles(findings))[0]
    row = card.damage_rows[0]
    assert row.title == finding.title
    assert row.detail == finding.detail


def test_a_card_only_takes_damage_findings_naming_that_player() -> None:
    findings = (a_finding("players.damage.0", title="Someoneelse took 4.1x the group median"),)
    card = build_players(a_loaded(), findings, None, a_player(), titles(findings))[0]
    assert ids(card.damage_rows) == []


def test_two_players_sharing_a_name_each_get_their_own_damage_row() -> None:
    # Cross-realm groups ordinarily produce two players with the same display
    # name; `display_names` disambiguates the second with its actor id, and the
    # finding's title is built the same way, so the match stays exact.
    loaded = a_loaded(players=(a_player(1, "Bob"), a_player(5, "Bob")))
    findings = (
        a_finding(
            "players.damage.0",
            title="Bob (actor 5) took 3.2x the group median from Whirlwind",
        ),
    )
    cards = build_players(loaded, findings, None, a_player(1, "Bob"), titles(findings))
    assert ids(cards[0].damage_rows) == []
    assert ids(cards[1].damage_rows) == ["players.damage.0"]


def test_one_players_name_being_a_prefix_of_anothers_does_not_misattribute_damage() -> None:
    loaded = a_loaded(players=(a_player(1, "Ann"), a_player(2, "Anna")))
    findings = (
        a_finding(
            "players.damage.0",
            title="Anna took 4.0x the group median from Frostbolt",
        ),
    )
    cards = build_players(loaded, findings, None, a_player(1, "Ann"), titles(findings))
    ann_card = next(card for card in cards if card.name == "Ann")
    anna_card = next(card for card in cards if card.name == "Anna")
    assert ids(ann_card.damage_rows) == []
    assert ids(anna_card.damage_rows) == ["players.damage.0"]


def test_without_a_parse_reference_the_comparison_half_is_withheld() -> None:
    card = build_players(a_loaded(), (), None, a_player(), {})[0]
    assert card.spell_and_talent.state is SectionState.WITHHELD
    assert card.spell_and_talent.reason
    assert card.spell_and_talent_rows == ()


def test_the_subjects_card_gets_the_comparison_rows_when_a_parse_reference_exists() -> None:
    # `a_parse()`'s top parser is a name that is not on our roster at all --
    # proof that the match is by actor id, never by the reference's own name.
    findings = (a_finding("compare.spells.missing.0", title="Missing Frost Nova"),)
    card = build_players(a_loaded(), findings, a_parse(), a_player(), titles(findings))[0]
    assert card.spell_and_talent.state is SectionState.PRESENT
    assert ids(card.spell_and_talent_rows) == ["compare.spells.missing.0"]


def test_a_non_subject_players_card_gets_no_comparison_rows() -> None:
    loaded = a_loaded(players=(a_player(1, "Dudesons"), a_player(2, "Other")))
    findings = (a_finding("compare.spells.missing.0", title="Missing Frost Nova"),)
    cards = build_players(
        loaded, findings, a_parse("Dudesons"), a_player(1, "Dudesons"), titles(findings)
    )
    other_card = next(card for card in cards if card.name == "Other")
    assert other_card.spell_and_talent_rows == ()


def test_the_comparison_rows_land_on_the_subject_not_a_namesake() -> None:
    # The reference run's top parser can share a display name with one of our
    # own players -- a different character in a different log. Matching by
    # actor id, not name, keeps the rows off that namesake and on the
    # analysed player's own card.
    loaded = a_loaded(players=(a_player(1, "Dudesons"), a_player(2, "Other")))
    findings = (a_finding("compare.spells.missing.0", title="Missing Frost Nova"),)
    cards = build_players(
        loaded, findings, a_parse("Dudesons"), a_player(2, "Other"), titles(findings)
    )
    namesake_card = next(card for card in cards if card.name == "Dudesons")
    subject_card = next(card for card in cards if card.name == "Other")
    assert namesake_card.spell_and_talent_rows == ()
    assert ids(subject_card.spell_and_talent_rows) == ["compare.spells.missing.0"]


def test_a_withheld_spell_comparison_finding_still_reaches_the_subjects_card() -> None:
    # When a run has no boss pulls, compare_spells returns only its own
    # `.unavailable` finding. That finding still explains the absence, so it
    # renders like any other row instead of being silently dropped.
    findings = (
        a_finding("compare.spells.unavailable", title="No boss pulls to compare"),
    )
    card = build_players(a_loaded(), findings, a_parse(), a_player(), titles(findings))[0]
    assert ids(card.spell_and_talent_rows) == ["compare.spells.unavailable"]


def test_a_card_states_casts_over_the_pull_time_they_happened_in() -> None:
    # a_loaded() carries one pull, 0 to 120_000ms, no casts, no deaths, no interrupts.
    card = build_players(a_loaded(), (), None, a_player(), {})[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 0 interrupts"


def test_a_cards_cast_count_cannot_read_as_a_percentage() -> None:
    # The old field claimed a share of pull time and could exceed 100%; the
    # replacement states a plain count over a plain duration, with no "%" in
    # sight to imply a bound the underlying model does not respect.
    card = build_players(a_loaded(), (), None, a_player(), {})[0]
    assert "%" not in card.stats_line


def test_a_single_cast_is_worded_in_the_singular() -> None:
    # One cast inside the pull window gives "1 cast", not "1 casts".
    loaded = a_loaded()
    loaded_with_cast = LoadedRun(
        run=loaded.run,
        casts=(CastEvent(actor_id=1, ability_id=1, ability_name="Whirlwind",
                          timestamp_ms=1_000, pull_index=0),),
    )
    card = build_players(loaded_with_cast, (), None, a_player(), {})[0]
    assert card.stats_line == "1 cast in 2:00 of pulls · 0 deaths · 0 interrupts"


def test_a_single_death_is_worded_in_the_singular() -> None:
    loaded = a_loaded()
    loaded_with_death = LoadedRun(
        run=loaded.run,
        deaths=(Death(player_name="Dudesons", actor_id=1, timestamp_ms=1_000,
                      killing_blow="Frigid Roar", pull_index=0),),
    )
    card = build_players(loaded_with_death, (), None, a_player(), {})[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 1 death · 0 interrupts"


def test_multiple_deaths_are_worded_in_the_plural() -> None:
    loaded = a_loaded()
    loaded_with_deaths = LoadedRun(
        run=loaded.run,
        deaths=(
            Death(player_name="Dudesons", actor_id=1, timestamp_ms=1_000,
                  killing_blow="Frigid Roar", pull_index=0),
            Death(player_name="Dudesons", actor_id=1, timestamp_ms=2_000,
                  killing_blow="Frigid Roar", pull_index=0),
        ),
    )
    card = build_players(loaded_with_deaths, (), None, a_player(), {})[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 2 deaths · 0 interrupts"


def test_a_single_interrupt_is_worded_in_the_singular() -> None:
    loaded = a_loaded()
    loaded_with_interrupt = LoadedRun(
        run=loaded.run,
        interrupts=(InterruptEvent(player_name="Dudesons", actor_id=1,
                                    interrupted_ability_id=1, target_id=1,
                                    target_instance=0, timestamp_ms=1_000, pull_index=0),),
    )
    card = build_players(loaded_with_interrupt, (), None, a_player(), {})[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 1 interrupt"


def test_multiple_interrupts_are_worded_in_the_plural() -> None:
    loaded = a_loaded()
    loaded_with_interrupts = LoadedRun(
        run=loaded.run,
        interrupts=(
            InterruptEvent(player_name="Dudesons", actor_id=1, interrupted_ability_id=1,
                            target_id=1, target_instance=0, timestamp_ms=1_000, pull_index=0),
            InterruptEvent(player_name="Dudesons", actor_id=1, interrupted_ability_id=2,
                            target_id=1, target_instance=0, timestamp_ms=2_000, pull_index=0),
        ),
    )
    card = build_players(loaded_with_interrupts, (), None, a_player(), {})[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 2 interrupts"

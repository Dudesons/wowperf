# ABOUTME: Behaviour tests for the interrupts section and the per-player cards.
# ABOUTME: A card carries a finding's title and detail unchanged; it adds no framing of its own.

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.events import CastEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.frame import NOT_REQUESTED
from wowperf.domain.report.ledger import place_rows
from wowperf.domain.report.model import LedgerRow, SectionState
from wowperf.domain.report.players import (
    build_players,
    class_colour,
    slugs_by_actor,
)
from wowperf.domain.season import CooldownAbility, Defensives, ThroughputCooldowns
from wowperf.domain.slug import player_slug


def a_finding(
    finding_id: str,
    seconds: float | None = None,
    title: str = "x",
    detail: str = "detail",
    slug: str = "",
) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        detail=detail,
        confidence=Confidence.DERIVED,
        seconds_lost=seconds,
        player_slug=slug,
    )


def titles(findings: tuple[Finding, ...]) -> dict[str, str]:
    return {finding.id: finding.title for finding in findings}


def a_player(actor_id: int = 1, name: str = "Stonewake") -> Player:
    return Player(
        actor_id=actor_id, name=name, class_name="DeathKnight", spec="Blood", item_level=680
    )


def a_loaded(players: tuple[Player, ...] | None = None) -> LoadedRun:
    return LoadedRun(
        run=a_run(players=players or (a_player(),), pulls=(a_pull(0, 0, 120_000),))
    )


def ids(rows: tuple[LedgerRow, ...]) -> list[str]:
    return [row.finding_id for row in rows]


def test_a_slug_survives_a_name_html_and_a_url_fragment_cannot_carry() -> None:
    assert player_slug("Bríala") == "briala"
    assert player_slug("Кириллица") != ""
    assert " " not in player_slug("Emberkin the Second")


def test_two_players_who_differ_only_by_realm_get_different_slugs() -> None:
    assert player_slug("Emberkin-Ravencrest") != player_slug("Emberkin-Silvermoon")


def test_every_card_carries_a_slug_and_no_two_cards_share_one() -> None:
    # Bríala and Briala reduce to the same slug -- the point of this test is
    # that the index the caller appends is what keeps their cards apart.
    loaded = a_loaded(
        players=(
            a_player(actor_id=1, name="Emberkin"),
            a_player(actor_id=2, name="Bríala"),
            a_player(actor_id=3, name="Briala"),
        ),
    )
    cards = build_players(
        loaded, (), None, a_player(actor_id=1, name="Emberkin"), {},
        Defensives(), ThroughputCooldowns(),
    )
    slugs = [card.slug for card in cards]
    assert all(slugs)
    assert len(set(slugs)) == len(slugs)


def test_the_subjects_card_comes_first_whatever_the_rosters_own_order() -> None:
    # The page opens whichever sub-tab is drawn first, so this ordering is what
    # decides which player a reader is shown. The subject is deliberately last
    # on the roster here: a builder that iterated the roster would put a
    # teammate's drawing in front of the reader who asked for their own.
    loaded = a_loaded(
        players=(
            a_player(actor_id=1, name="Emberkin"),
            a_player(actor_id=2, name="Bríala"),
            a_player(actor_id=3, name="Stonewake"),
        ),
    )
    cards = build_players(
        loaded, (), None, a_player(actor_id=3, name="Stonewake"), {},
        Defensives(), ThroughputCooldowns(),
    )
    assert [card.name for card in cards] == ["Stonewake", "Emberkin", "Bríala"]


def test_the_players_behind_the_subject_keep_the_rosters_order() -> None:
    # Only the subject moves. Sorting the rest -- by name, by damage, by
    # anything -- would rank them, which the postmortem design's section 5.5
    # refuses; a stable partition is what keeps the move to one card.
    loaded = a_loaded(
        players=(
            a_player(actor_id=1, name="Emberkin"),
            a_player(actor_id=2, name="Bríala"),
            a_player(actor_id=3, name="Stonewake"),
        ),
    )
    cards = build_players(
        loaded, (), None, a_player(actor_id=2, name="Bríala"), {},
        Defensives(), ThroughputCooldowns(),
    )
    assert [card.name for card in cards] == ["Bríala", "Emberkin", "Stonewake"]


def test_the_interrupts_section_takes_its_findings() -> None:
    findings = (a_finding("interrupts.summary"), a_finding("interrupts.ability.0"))
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == ["interrupts.summary", "interrupts.ability.0"]


def test_a_timed_interrupt_finding_lands_in_interrupts_too() -> None:
    # PLACEMENTS sends every "compare.interrupts" row to the Interrupts tab,
    # timed or not: there is no page-wide ledger of losses for it to go to instead.
    findings = (a_finding("compare.interrupts", seconds=40.0),)
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == ["compare.interrupts"]


def test_the_interrupts_section_takes_nothing_that_is_not_an_interrupt() -> None:
    findings = (a_finding("players.damage.0"),)
    rows = place_rows(findings, titles(findings), exclude=set())["interrupts"]
    assert ids(rows) == []


def test_one_card_per_player() -> None:
    cards = build_players(a_loaded(), (), None, a_player(), {}, Defensives(), ThroughputCooldowns())
    assert [card.name for card in cards] == ["Stonewake"]


def test_build_players_accepts_the_defensives_and_throughput_cooldowns_it_will_read() -> None:
    # Both parameters are unused today; the next task reads them. This proves
    # only that build_players takes them without disturbing its existing output.
    throughput = ThroughputCooldowns(
        entries=(("DeathKnight/Blood", (CooldownAbility(
            ability_id=1, name="Dancing Rune Weapon", cooldown_seconds=120.0
        ),)),)
    )
    cards = build_players(a_loaded(), (), None, a_player(), {}, Defensives(), throughput)
    assert [card.name for card in cards] == ["Stonewake"]


def test_two_players_sharing_a_name_get_disambiguated_card_names() -> None:
    # Two visually identical cards for two different people is exactly what a
    # shared display name must not produce; the actor id disambiguates both,
    # the same way `display_names` disambiguates the finding titles that name them.
    loaded = a_loaded(players=(a_player(1, "Sublime"), a_player(5, "Sublime")))
    cards = build_players(
        loaded, (), None, a_player(1, "Sublime"), {}, Defensives(), ThroughputCooldowns()
    )
    assert [card.name for card in cards] == ["Sublime (actor 1)", "Sublime (actor 5)"]


def test_a_card_names_the_class_in_text_beside_its_colour() -> None:
    card = build_players(
        a_loaded(), (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.class_name == "DeathKnight"
    assert card.colour == class_colour("DeathKnight")
    assert card.colour != card.class_name


def test_an_unknown_class_still_gets_a_colour_rather_than_an_empty_string() -> None:
    assert class_colour("Bard") == "class-unknown"


def test_a_card_carries_its_players_damage_findings() -> None:
    findings = (a_finding("players.damage.0", title="Stonewake took 2.3x the group median"),)
    card = build_players(
        a_loaded(), findings, None, a_player(), titles(findings), Defensives(),
        ThroughputCooldowns(),
    )[0]
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
        title="Stonewake took 2.3x the group median from Rending Slash",
        detail=detail,
    )
    findings = (finding,)
    card = build_players(
        a_loaded(), findings, None, a_player(), titles(findings), Defensives(),
        ThroughputCooldowns(),
    )[0]
    row = card.damage_rows[0]
    assert row.title == finding.title
    assert row.detail == finding.detail


def test_a_card_only_takes_damage_findings_naming_that_player() -> None:
    findings = (a_finding("players.damage.0", title="Someoneelse took 4.1x the group median"),)
    card = build_players(
        a_loaded(), findings, None, a_player(), titles(findings), Defensives(),
        ThroughputCooldowns(),
    )[0]
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
    cards = build_players(
        loaded, findings, None, a_player(1, "Bob"), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )
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
    cards = build_players(
        loaded, findings, None, a_player(1, "Ann"), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )
    ann_card = next(card for card in cards if card.name == "Ann")
    anna_card = next(card for card in cards if card.name == "Anna")
    assert ids(ann_card.damage_rows) == []
    assert ids(anna_card.damage_rows) == ["players.damage.0"]


def test_without_a_comparison_at_all_the_comparison_half_is_withheld() -> None:
    card = build_players(
        a_loaded(), (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.spell_and_talent.state is SectionState.WITHHELD
    assert card.spell_and_talent.reason
    assert card.spell_and_talent_rows == ()


def test_a_compared_players_card_gets_the_comparison_rows() -> None:
    findings = (
        a_finding(
            "compare.spells.missing.0.stonewake-0",
            title="Missing Frost Nova",
            slug="stonewake-0",
        ),
    )
    card = build_players(
        a_loaded(), findings, frozenset({"stonewake-0"}), a_player(), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )[0]
    assert card.spell_and_talent.state is SectionState.PRESENT
    assert ids(card.spell_and_talent_rows) == ["compare.spells.missing.0.stonewake-0"]


def test_an_uncompared_players_card_gets_no_comparison_rows() -> None:
    loaded = a_loaded(players=(a_player(1, "Stonewake"), a_player(2, "Other")))
    findings = (
        a_finding(
            "compare.spells.missing.0.stonewake-0",
            title="Missing Frost Nova",
            slug="stonewake-0",
        ),
    )
    cards = build_players(
        loaded, findings, frozenset({"stonewake-0"}), a_player(1, "Stonewake"), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )
    other_card = next(card for card in cards if card.name == "Other")
    assert other_card.spell_and_talent_rows == ()


def test_the_comparison_rows_land_on_the_player_they_name_not_on_the_subject() -> None:
    # The subject decides which card is drawn first and nothing else. A run can
    # compare a player the reader did not name -- or, once several players are
    # compared, several at once -- so the rows follow the slug each finding
    # carries rather than whoever the report is addressed to.
    loaded = a_loaded(players=(a_player(1, "Stonewake"), a_player(2, "Other")))
    findings = (
        a_finding(
            "compare.spells.missing.0.other-1", title="Missing Frost Nova", slug="other-1"
        ),
    )
    cards = build_players(
        loaded, findings, frozenset({"other-1"}), a_player(1, "Stonewake"), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )
    subject_card = next(card for card in cards if card.name == "Stonewake")
    compared_card = next(card for card in cards if card.name == "Other")
    assert subject_card.spell_and_talent_rows == ()
    assert ids(compared_card.spell_and_talent_rows) == ["compare.spells.missing.0.other-1"]


def test_a_withheld_spell_comparison_finding_still_reaches_that_players_card() -> None:
    # When a run has no boss pulls, compare_spells returns only its own
    # `.unavailable` finding. That finding still explains the absence, so it
    # renders like any other row instead of being silently dropped.
    findings = (
        a_finding(
            "compare.spells.unavailable.stonewake-0",
            title="No boss pulls to compare",
            slug="stonewake-0",
        ),
    )
    card = build_players(
        a_loaded(), findings, frozenset({"stonewake-0"}), a_player(), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )[0]
    assert ids(card.spell_and_talent_rows) == ["compare.spells.unavailable.stonewake-0"]


def test_a_card_states_casts_over_the_pull_time_they_happened_in() -> None:
    # a_loaded() carries one pull, 0 to 120_000ms, no casts, no deaths, no interrupts.
    card = build_players(
        a_loaded(), (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 0 interrupts"


def test_a_cards_cast_count_cannot_read_as_a_percentage() -> None:
    # The old field claimed a share of pull time and could exceed 100%; the
    # replacement states a plain count over a plain duration, with no "%" in
    # sight to imply a bound the underlying model does not respect.
    card = build_players(
        a_loaded(), (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert "%" not in card.stats_line


def test_a_single_cast_is_worded_in_the_singular() -> None:
    # One cast inside the pull window gives "1 cast", not "1 casts".
    loaded = a_loaded()
    loaded_with_cast = LoadedRun(
        run=loaded.run,
        casts=(CastEvent(actor_id=1, ability_id=1, ability_name="Whirlwind",
                          timestamp_ms=1_000, pull_index=0),),
    )
    card = build_players(
        loaded_with_cast, (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "1 cast in 2:00 of pulls · 0 deaths · 0 interrupts"


def test_a_single_death_is_worded_in_the_singular() -> None:
    loaded = a_loaded()
    loaded_with_death = LoadedRun(
        run=loaded.run,
        deaths=(Death(player_name="Stonewake", actor_id=1, timestamp_ms=1_000,
                      killing_blow="Frigid Roar", pull_index=0),),
    )
    card = build_players(
        loaded_with_death, (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 1 death · 0 interrupts"


def test_multiple_deaths_are_worded_in_the_plural() -> None:
    loaded = a_loaded()
    loaded_with_deaths = LoadedRun(
        run=loaded.run,
        deaths=(
            Death(player_name="Stonewake", actor_id=1, timestamp_ms=1_000,
                  killing_blow="Frigid Roar", pull_index=0),
            Death(player_name="Stonewake", actor_id=1, timestamp_ms=2_000,
                  killing_blow="Frigid Roar", pull_index=0),
        ),
    )
    card = build_players(
        loaded_with_deaths, (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 2 deaths · 0 interrupts"


def test_a_single_interrupt_is_worded_in_the_singular() -> None:
    loaded = a_loaded()
    loaded_with_interrupt = LoadedRun(
        run=loaded.run,
        interrupts=(InterruptEvent(player_name="Stonewake", actor_id=1,
                                    interrupted_ability_id=1, target_id=1,
                                    target_instance=0, timestamp_ms=1_000, pull_index=0),),
    )
    card = build_players(
        loaded_with_interrupt, (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 1 interrupt"


def test_multiple_interrupts_are_worded_in_the_plural() -> None:
    loaded = a_loaded()
    loaded_with_interrupts = LoadedRun(
        run=loaded.run,
        interrupts=(
            InterruptEvent(player_name="Stonewake", actor_id=1, interrupted_ability_id=1,
                            target_id=1, target_instance=0, timestamp_ms=1_000, pull_index=0),
            InterruptEvent(player_name="Stonewake", actor_id=1, interrupted_ability_id=2,
                            target_id=1, target_instance=0, timestamp_ms=2_000, pull_index=0),
        ),
    )
    card = build_players(
        loaded_with_interrupts, (), None, a_player(), {}, Defensives(), ThroughputCooldowns()
    )[0]
    assert card.stats_line == "0 casts in 2:00 of pulls · 0 deaths · 2 interrupts"


def test_two_names_that_reduce_to_one_slug_stay_apart() -> None:
    # Bríala and Briala both reduce to "briala"; the roster index separates them.
    run = a_run(
        players=(a_player(actor_id=1, name="Bríala"), a_player(actor_id=2, name="Briala")),
        pulls=(a_pull(0, 0, 120_000),),
    )
    slugs = slugs_by_actor(run)
    assert slugs[1] != slugs[2]
    assert slugs[1].startswith("briala")
    assert slugs[2].startswith("briala")


def test_a_findings_slug_addresses_the_card_that_carries_it() -> None:
    # `slugs_by_actor` exists so the comparison and the card cannot compute a
    # slug independently and drift. This is the test that fails if they ever do.
    # Bríala and Briala reduce to one slug before the roster index is appended,
    # so a builder that dropped the index would land these rows on either card.
    first = a_player(actor_id=1, name="Bríala")
    second = a_player(actor_id=2, name="Briala")
    loaded = a_loaded(players=(first, second))
    slugs = slugs_by_actor(loaded.run)
    hers = Finding(
        id=f"compare.talents.{slugs[2]}", title="theirs", detail="d",
        confidence=Confidence.MEASURED, player_slug=slugs[2],
    )
    cards = build_players(
        loaded, (hers,), frozenset(slugs.values()), first, titles((hers,)),
        Defensives(), ThroughputCooldowns(),
    )
    carrying = [card for card in cards if card.spell_and_talent_rows]
    assert len(carrying) == 1
    assert carrying[0].slug == slugs[2]
    assert carrying[0].name != "Bríala"


def test_a_slug_does_not_change_when_a_different_player_is_the_subject() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    findings: tuple[Finding, ...] = ()

    subject_first = build_players(
        loaded, findings, frozenset({"emberkin-0"}), first, {}, Defensives(), ThroughputCooldowns()
    )
    subject_second = build_players(
        loaded, findings, frozenset({"stonewake-1"}), second, {}, Defensives(),
        ThroughputCooldowns(),
    )

    by_name_first = {card.name: card.slug for card in subject_first}
    by_name_second = {card.name: card.slug for card in subject_second}
    assert by_name_first == by_name_second


def test_a_player_nobody_asked_for_says_so_rather_than_implying_an_empty_leaderboard() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    cards = build_players(
        loaded, (), frozenset({"emberkin-0"}), first, {}, Defensives(), ThroughputCooldowns()
    )
    theirs = next(card for card in cards if card.name == "Stonewake")
    assert theirs.spell_and_talent.state is SectionState.WITHHELD
    assert theirs.spell_and_talent.reason == NOT_REQUESTED


def test_no_comparison_at_all_reads_differently_from_a_player_nobody_asked_for() -> None:
    loaded = a_loaded(players=(a_player(actor_id=1, name="Emberkin"),))
    cards = build_players(
        loaded, (), None, a_player(actor_id=1, name="Emberkin"), {},
        Defensives(), ThroughputCooldowns(),
    )
    assert cards[0].spell_and_talent.reason != NOT_REQUESTED


def test_each_player_gets_only_their_own_comparison_rows() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    mine = Finding(
        id="compare.talents.emberkin-0", title="mine", detail="d",
        confidence=Confidence.MEASURED, player_slug="emberkin-0",
    )
    theirs = Finding(
        id="compare.talents.stonewake-1", title="theirs", detail="d",
        confidence=Confidence.MEASURED, player_slug="stonewake-1",
    )
    cards = build_players(
        loaded, (mine, theirs), frozenset({"emberkin-0", "stonewake-1"}), first,
        titles((mine, theirs)), Defensives(), ThroughputCooldowns(),
    )
    by_name = {card.name: ids(card.spell_and_talent_rows) for card in cards}
    assert by_name["Emberkin"] == ["compare.talents.emberkin-0"]
    assert by_name["Stonewake"] == ["compare.talents.stonewake-1"]


def test_one_player_is_withheld_while_another_is_present() -> None:
    first = a_player(actor_id=1, name="Emberkin")
    second = a_player(actor_id=2, name="Stonewake")
    loaded = a_loaded(players=(first, second))
    mine = Finding(
        id="compare.talents.emberkin-0", title="mine", detail="d",
        confidence=Confidence.MEASURED, player_slug="emberkin-0",
    )
    refused = Finding(
        id="compare.parse.unavailable.stonewake-1", title="none",
        detail="The score leaderboard returned nothing.",
        confidence=Confidence.MEASURED, player_slug="stonewake-1",
    )
    cards = build_players(
        loaded, (mine, refused), frozenset({"emberkin-0", "stonewake-1"}), first,
        titles((mine, refused)), Defensives(), ThroughputCooldowns(),
    )
    by_name = {card.name: card.spell_and_talent for card in cards}
    assert by_name["Emberkin"].state is SectionState.PRESENT
    assert by_name["Stonewake"].state is SectionState.WITHHELD
    assert by_name["Stonewake"].reason == "The score leaderboard returned nothing."


def test_a_trash_spell_row_lands_under_the_players_card() -> None:
    """COMPARISON_PREFIXES matches on "compare.spells.", so the trash family is
    routed by the same rule as the boss rows. Pinned because a family that fell
    through would land in the Summary catch-all without failing anything else."""
    findings = (
        a_finding(
            "compare.spells.trash.rate.0.stonewake-0",
            title="3 top parses cast Blood Boil a median 9.1 times a minute across "
            "4 aligned packs; Stonewake casts it 6.0",
            slug="stonewake-0",
        ),
    )
    card = build_players(
        a_loaded(), findings, frozenset({"stonewake-0"}), a_player(), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )[0]

    assert card.spell_and_talent.state is SectionState.PRESENT
    assert ids(card.spell_and_talent_rows) == ["compare.spells.trash.rate.0.stonewake-0"]


def test_an_above_row_lands_under_the_players_card() -> None:
    """The reverse direction routes by the same "compare.spells." prefix. Pinned
    separately because a family that fell through would land in the Summary
    catch-all without failing anything else."""
    findings = (
        a_finding(
            "compare.spells.above.0.stonewake-0",
            title="Stonewake casts Marrowrend 2.9 times a minute on bosses; "
            "5 top parses cast it a median 1.3",
            slug="stonewake-0",
        ),
    )
    card = build_players(
        a_loaded(), findings, frozenset({"stonewake-0"}), a_player(), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )[0]

    assert card.spell_and_talent.state is SectionState.PRESENT
    assert ids(card.spell_and_talent_rows) == ["compare.spells.above.0.stonewake-0"]

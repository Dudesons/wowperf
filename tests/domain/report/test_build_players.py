# ABOUTME: Behaviour tests for the interrupts section and the per-player cards.
# ABOUTME: A card carries a finding's title and detail unchanged; it adds no framing of its own.

import pytest

from tests.domain.report.test_build_frame import a_pull, a_run
from wowperf.domain.comparison.boss_debuffs import Withheld
from wowperf.domain.comparison.measures import (
    AbilityRate,
    AuraRow,
    AuraUptime,
    BossCell,
    DebuffReach,
    DebuffRow,
    DebuffTable,
    PlayerMeasures,
    StatShare,
    Stretch,
    StretchCell,
    Verdict,
)
from wowperf.domain.debuffs import PairingTally
from wowperf.domain.events import CastEvent, Death, InterruptEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import LoadedRun, Player
from wowperf.domain.report.frame import NOT_REQUESTED
from wowperf.domain.report.ledger import place_rows
from wowperf.domain.report.model import ComparisonTable, LedgerRow, PlayerCard, SectionState
from wowperf.domain.report.players import (
    VERDICT_LABELS,
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
    loaded = a_loaded(players=(a_player(1, "Bríala"), a_player(5, "Bríala")))
    cards = build_players(
        loaded, (), None, a_player(1, "Bríala"), {}, Defensives(), ThroughputCooldowns()
    )
    assert [card.name for card in cards] == ["Bríala (actor 1)", "Bríala (actor 5)"]


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
    slugs = slugs_by_actor(run.players)
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
    slugs = slugs_by_actor(loaded.run.players)
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


def test_the_gear_stat_and_consumable_families_land_on_a_player_card() -> None:
    """COMPARISON_PREFIXES routes compare.gear., compare.stats. and
    compare.consumables. the same way it already routes compare.spells. --
    checked against `build_players` itself rather than against the prefix
    tuple alone, so a routing rule elsewhere that intercepted one of these ids
    before it reached `comparison` -- landing it in the ledger instead of the
    player's card -- would still be caught."""
    findings = (
        a_finding("compare.gear.enchant.7.stonewake-0", slug="stonewake-0"),
        a_finding("compare.gear.tier.stonewake-0", slug="stonewake-0"),
        a_finding("compare.stats.rating.stonewake-0", slug="stonewake-0"),
        a_finding("compare.consumables.buff.flask.stonewake-0", slug="stonewake-0"),
        a_finding("compare.consumables.potion.stonewake-0", slug="stonewake-0"),
    )
    card = build_players(
        a_loaded(), findings, frozenset({"stonewake-0"}), a_player(), titles(findings),
        Defensives(), ThroughputCooldowns(),
    )[0]

    assert card.spell_and_talent.state is SectionState.PRESENT
    assert set(ids(card.spell_and_talent_rows)) == {finding.id for finding in findings}


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


def test_a_compared_players_card_carries_its_tables_sorted_by_gap() -> None:
    """The top of each table is the end worth reading, so the largest difference
    comes first whichever direction it runs in."""
    measures = {
        "stonewake-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Small gap", ours=9.0, their_median=10.0,
                            their_rates=(10.0,), stretch=Stretch.BOSS, verdict=Verdict.LEVEL),
                AbilityRate(ability_id=2, name="Big gap", ours=2.0, their_median=9.0,
                            their_rates=(9.0,), stretch=Stretch.BOSS, verdict=Verdict.BELOW),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    boss = next(t for t in card.comparison_tables if "boss" in t.heading.lower())
    assert [row.name for row in boss.rows] == ["Big gap", "Small gap"]
    assert boss.rows[0].ours == "2.0"
    assert boss.rows[0].theirs == "9.0"
    assert boss.rows[0].verdict == "below"


def test_a_rate_row_states_every_field_to_one_decimal_place() -> None:
    """The sort-order test above uses whole numbers, which print the same whether
    or not each figure is rounded to one decimal place; this uses fractional ones
    so every field's own formatting is what the assertion actually depends on."""
    measures = {
        "stonewake-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Only ability", ours=2.34, their_median=9.06,
                            their_rates=(7.02, 9.06, 11.04), stretch=Stretch.BOSS,
                            verdict=Verdict.BELOW),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    row = next(t for t in card.comparison_tables if "boss" in t.heading.lower()).rows[0]
    assert row.ours == "2.3"
    assert row.theirs == "9.1"
    assert row.spread == "7.0 to 11.0"
    assert row.sample == "3 top parses"


def test_a_zero_boss_denominator_beside_a_real_trash_one_only_shows_the_trash_table() -> None:
    """`_boss` can return no rates and a boss_seconds of 0.0 while `_trash` still
    carries a real denominator, because trash has no aggregate-size gate of its
    own. A heading built over "0s of boss pulls" would be wrong; dropping a table
    that has no rows -- which an empty `boss` always pairs with here -- is what
    keeps that from being built at all."""
    measures = {
        "stonewake-0": PlayerMeasures(
            trash=(
                AbilityRate(ability_id=1, name="Blood Boil", ours=6.0, their_median=9.1,
                            their_rates=(9.1, 8.4, 9.9), stretch=Stretch.TRASH,
                            verdict=Verdict.BELOW),
            ),
            boss_seconds=0.0,
            trash_seconds=950.0,
            pack_count=4,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    assert [t.heading for t in card.comparison_tables] == ["Casts on shared trash packs"]


def test_an_uncompared_player_gets_no_tables() -> None:
    card = build_players(
        a_loaded(), (), frozenset(), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures={},
    )[0]

    assert card.comparison_tables == ()


def test_an_uptime_table_is_sorted_by_our_own_uptime_not_by_the_gap() -> None:
    """The cast tables lead with the widest gap. This one leads with what the
    player actually held, highest first, because it is read as a list of "how
    much of the fight did I have this up for" and a reader scans it top to
    bottom.

    The fixture is built so the two rules disagree: the row with the widest gap
    is the one with the lowest uptime, so a table still sorting by gap would
    come out exactly reversed.
    """
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(uptime=AuraUptime(
                    ability_id=2, name="Big gap", ours=0.40, their_median=1.0,
                    their_fractions=(1.0,), verdict=Verdict.BELOW,
                )),
                AuraRow(uptime=AuraUptime(
                    ability_id=1, name="Small gap", ours=0.95, their_median=1.0,
                    their_fractions=(1.0,), verdict=Verdict.LEVEL,
                )),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    auras = next(t for t in card.comparison_tables if "uptime" in t.heading.lower())
    assert [row.name for row in auras.rows] == ["Small gap", "Big gap"]


def test_an_uptime_row_is_spelled_as_a_percentage() -> None:
    """Rates are casts a minute and uptimes are a share of the key's time. A column
    that spelled both the same way would invite reading one as the other."""
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(uptime=AuraUptime(
                    ability_id=3, name="Bone Shield", ours=0.984,
                    their_median=1.0, their_fractions=(1.0,), verdict=Verdict.LEVEL,
                )),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    auras = next(t for t in card.comparison_tables if "uptime" in t.heading.lower())
    assert auras.rows[0].cells[0] == "98% against 100%"


def test_an_uptime_rows_range_and_sample_state_its_overall_figure() -> None:
    """The row's own cells hold other medians and other counts. The spread and
    the sample beside the verdict are the judged Overall figure's references,
    two parses here, and neither stretch cell's."""
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=3, name="Bone Shield", ours=0.5, their_median=0.6,
                        their_fractions=(0.4, 0.8), verdict=Verdict.LEVEL,
                    ),
                    without_bosses=StretchCell(ours=0.1, their_median=0.2),
                    bosses=StretchCell(ours=0.9, their_median=0.95),
                ),
            ),
            boss_seconds=600.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [row] = next(t for t in card.comparison_tables if "uptime" in t.heading.lower()).rows
    assert row.cells[:3] == ("50% against 60%", "40% to 80%", "2 top parses")


def a_card_with_all_three_tables() -> PlayerCard:
    """One card carrying every table at once, over denominators that differ.

    648 boss seconds, 950 trash seconds and 8 packs are three distinct numbers,
    so a caption that reached for the wrong one of them reads as a different
    sentence rather than the same one by coincidence. Each table holds one row,
    which is all the caption assertions need and keeps the sort order out of
    them.
    """
    measures = {
        "stonewake-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=50842, name="Blood Boil", ours=6.0, their_median=9.1,
                            their_rates=(8.4, 9.1, 9.9), stretch=Stretch.BOSS,
                            verdict=Verdict.BELOW),
            ),
            trash=(
                AbilityRate(ability_id=195182, name="Marrowrend", ours=2.9, their_median=1.3,
                            their_rates=(1.1, 1.3, 1.6), stretch=Stretch.TRASH,
                            verdict=Verdict.ABOVE),
            ),
            auras=(
                AuraRow(uptime=AuraUptime(
                    ability_id=195181, name="Bone Shield", ours=0.62,
                    their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                    verdict=Verdict.BELOW,
                )),
            ),
            boss_seconds=648.0,
            trash_seconds=950.0,
            pack_count=8,
            key_seconds=1834.0,
        )
    }
    return build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]


def test_the_three_tables_come_under_their_own_headings_in_one_order() -> None:
    """Each heading is pinned exactly rather than by a substring, and all three
    are read as a sequence. Two tables swapping places would leave a reader the
    denominator of the other one's caption; a heading loosened to a word both
    share would stop saying which table is which at all."""
    assert [t.heading for t in a_card_with_all_three_tables().comparison_tables] == [
        "Casts on boss pulls",
        "Casts on shared trash packs",
        "Buff uptime",
    ]


def test_the_table_captions_are_not_interchangeable() -> None:
    """A caption is a claim about which stretch its figures were drawn over, so
    the boss caption under the trash table misdescribes both. Checking that each
    caption is non-empty would not catch the swap; this pins each caption's exact
    words against its own denominator, the way
    `test_build_player_timeline.test_the_badge_captions_are_not_interchangeable`
    pins each of those against its own badge.

    The word "Derived." is part of every one of them: the table is a page of
    divisions, and the project badges every claim it makes.
    """
    boss, trash, auras = a_card_with_all_three_tables().comparison_tables

    assert boss.caption == (
        "Casts a minute over 648s of boss pulls, against the median of the "
        "parses that cast each. Derived."
    )
    assert trash.caption == (
        "Casts a minute over 950s of trash across 8 packs both routes fought, "
        "against the median of the parses that cast each. Derived."
    )
    assert auras.caption == (
        "Share of 1834s of key time, from the key's start to its end with the walking "
        "between pulls included, against the median of the parses that carried each. The "
        "verdict reads Overall, and Range and Sample are Overall's. Without bosses is the key "
        "less its boss pulls and Bosses the boss pulls; each reads ours against the median "
        "and carries no verdict. A buff only up in combat reads lower over the whole key the "
        "more of it was spent between pulls, so a reference that walked less reads higher "
        "whatever either player did. Derived."
    )
    assert len({boss.caption, trash.caption, auras.caption}) == 3


def test_every_row_carries_the_ability_id_its_measure_named() -> None:
    """The id is the icon key, and a name is not one: a zeroed or swapped id
    draws the wrong art beside the right name, which is the single failure a
    name-only assertion cannot see. Both builders mint their own row, so both
    are read here."""
    boss, trash, auras = a_card_with_all_three_tables().comparison_tables

    assert [(row.name, row.ability_id) for row in boss.rows] == [("Blood Boil", 50842)]
    assert [(row.name, row.ability_id) for row in trash.rows] == [("Marrowrend", 195182)]
    assert [(row.name, row.ability_id) for row in auras.rows] == [("Bone Shield", 195181)]


def test_an_aura_the_comparison_refused_to_judge_keeps_that_verdict() -> None:
    """`_aura_rows` is `_rate_rows`'s twin and mints every field over again, so
    the rate side's coverage says nothing about it.

    `UNJUDGED` is reached by auras alone: `onSelf` carries no source, so an aura
    we show none of may be a teammate's buff nobody gave this player. A row
    rendered as `level` instead would style that silence as a measured match,
    and `.compared-rows tr.v-unjudged` would match nothing on the page.
    """
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(uptime=AuraUptime(
                    ability_id=1459, name="Arcane Intellect", ours=0.0,
                    their_median=0.97, their_fractions=(0.94, 0.97, 0.99),
                    verdict=Verdict.UNJUDGED,
                )),
            ),
            boss_seconds=648.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    row = card.comparison_tables[0].rows[0]
    assert row.verdict == "unjudged"
    assert row.cells[1:3] == ("94% to 99%", "3 top parses")


def test_each_verdict_reaches_a_row_as_its_own_word() -> None:
    """The word and the tint are two readings of one branch, so they must not be
    able to say opposite things about it.

    Every other assertion about a verdict reads both halves off the same row --
    the class against `row.verdict`, the cell against `row.verdict_label` -- and
    is therefore true of any mapping at all, permuted ones included. Two labels
    trading places leaves each row still internally consistent and still
    different from its neighbour, and a reader who cannot separate the two
    tints, which is the reader the column exists for, would be told the reverse
    of the truth. This is what pins the branch to its English, each of the four
    to its own, against words written out here rather than read back off the
    map.
    """
    measures = {
        "stonewake-0": PlayerMeasures(
            boss=(
                AbilityRate(ability_id=1, name="Under", ours=2.0, their_median=9.0,
                            their_rates=(9.0,), stretch=Stretch.BOSS, verdict=Verdict.BELOW),
                AbilityRate(ability_id=2, name="Over", ours=9.0, their_median=2.0,
                            their_rates=(2.0,), stretch=Stretch.BOSS, verdict=Verdict.ABOVE),
                AbilityRate(ability_id=3, name="Alongside", ours=5.0, their_median=5.0,
                            their_rates=(5.0,), stretch=Stretch.BOSS, verdict=Verdict.LEVEL),
            ),
            # No cast rate is ever unjudged -- a cast is unambiguously the
            # player's own -- so the fourth branch is asked of the builder that
            # can really produce it.
            auras=(
                AuraRow(uptime=AuraUptime(
                    ability_id=4, name="Someone's buff", ours=0.0, their_median=0.97,
                    their_fractions=(0.97,), verdict=Verdict.UNJUDGED,
                )),
            ),
            boss_seconds=648.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]
    boss, auras = card.comparison_tables

    # A set, because `_rate_rows` orders by the size of the gap and this says
    # nothing about order. Exact equality: it pins that no branch borrowed
    # another's word just as much as that each kept its own.
    assert {(row.verdict, row.verdict_label) for row in boss.rows} == {
        ("below", "Below"),
        ("above", "Above"),
        ("level", "Level"),
    }
    assert [(row.verdict, row.verdict_label) for row in auras.rows] == [
        ("unjudged", "Not judged")
    ]
    # A branch added with no word would reach `VERDICT_LABELS` as a KeyError at
    # render time, on a page nobody is running a test against.
    assert set(VERDICT_LABELS) == set(Verdict)


def a_card_with_a_stat_table() -> PlayerCard:
    measures = {
        "stonewake-0": PlayerMeasures(
            stats=(
                StatShare(name="crit", ours=0.42, their_median=0.31,
                          their_shares=(0.29, 0.31, 0.33), our_rating=1183,
                          their_median_rating=1402.0,
                          their_ratings=(1310.0, 1402.0, 1490.0), verdict=Verdict.ABOVE),
                StatShare(name="mastery", ours=0.11, their_median=0.24,
                          their_shares=(0.22, 0.24, 0.27), our_rating=310,
                          their_median_rating=1090.0,
                          their_ratings=(990.0, 1090.0, 1220.0), verdict=Verdict.BELOW),
            ),
        )
    }
    return build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]


def test_a_stat_row_carries_the_share_the_rating_and_no_ability() -> None:
    """Both figures in one cell, because the share is the judgement and the
    rating is the fact a reader recognises. The share is what "balance" means
    and what item level cannot explain; the rating alone would put every row
    below the sample on gear difference alone.

    `ability_id` is None rather than a stand-in id: a stat has no spell behind
    it, and a stand-in would draw whatever art that id happened to address.
    """
    table = next(t for t in a_card_with_a_stat_table().comparison_tables
                 if "stat" in t.heading.lower())
    crit, mastery = table.rows

    assert crit.name == "Crit"
    assert crit.ours == "42% (1183)"
    assert crit.theirs == "31% (1402)"
    assert crit.spread == "29% to 33%"
    assert crit.sample == "3 top parses"
    assert crit.verdict == "above"
    assert crit.ability_id is None

    # The second row differs in every column, so a cell printing its
    # neighbour's value cannot pass the block above by coincidence.
    assert mastery.name == "Mastery"
    assert mastery.ours == "11% (310)"
    assert mastery.verdict == "below"


def test_the_stat_table_keeps_the_order_the_stats_were_held_in() -> None:
    # The three tables above sort by widest gap. This one must not: a balance is
    # read down a column, and mastery's gap here is wider than crit's, so a sort
    # would swap them and this test would see it.
    table = next(t for t in a_card_with_a_stat_table().comparison_tables
                 if "stat" in t.heading.lower())
    assert [row.name for row in table.rows] == ["Crit", "Mastery"]


def test_a_player_with_no_readable_stats_gets_no_stat_table() -> None:
    # An empty table and a missing one are different claims. Withholding it is
    # what the report does everywhere else the data was never fetched.
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures={"stonewake-0": PlayerMeasures()},
    )[0]
    assert not [t for t in card.comparison_tables if "stat" in t.heading.lower()]


def test_a_debuff_table_with_no_rows_and_no_stream_is_not_drawn() -> None:
    # Our stream failing leaves `tally` None, and the caption that reads it is
    # only ever built beside rows, so the page never meets the None.
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(),
        measures={"stonewake-0": PlayerMeasures(debuffs=DebuffTable())},
    )[0]

    assert not [t for t in card.comparison_tables if "Debuff" in t.heading]


def test_the_debuff_tables_follow_the_buff_table_with_a_column_per_stretch_and_boss() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    )
                ),
            ),
            boss_seconds=648.0,
            key_seconds=1834.0,
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.7,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        trash=StretchCell(ours=0.4, their_median=0.8),
                        bosses=StretchCell(ours=0.6, their_median=0.9),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.5,
                                their_median=0.9,
                            ),
                            BossCell(
                                encounter_id=2002, boss="Second Boss",
                                withheld=Withheld.NO_BOSS,
                            ),
                            BossCell(
                                encounter_id=2003, boss="Third Boss", ours=0.8,
                                withheld=Withheld.TOO_FEW,
                            ),
                        ),
                    ),
                ),
                seconds=200.0,
                bosses=("First Boss", "Second Boss", "Third Boss"),
                tally=PairingTally(orphan_removes=1, closed_at_end=2),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    assert [t.heading for t in card.comparison_tables] == [
        "Buff uptime",
        "Debuff coverage",
        "Debuff reach",
    ]
    table = card.comparison_tables[1]
    assert (table.figures, table.judged) == (False, True)
    assert table.cell_headings == (
        "Overall",
        "Range",
        "Sample",
        "Trash",
        "Bosses",
        "First Boss",
        "Second Boss",
        "Third Boss",
    )
    [row] = table.rows
    assert row.verdict_label == "Below"
    # Drawn once, in the cells: the row's own figure strings stay empty on a
    # table that draws no figure columns.
    assert (row.ours, row.theirs, row.spread, row.sample) == ("", "", "", "")
    # Range and Sample are Overall's: the references' 85%, 90% and 95%. Neither
    # stretch nor any boss cell carries a range of its own.
    assert row.cells == (
        "70% against 90%",
        "85% to 95%",
        "3 top parses",
        "40% against 80%",
        "60% against 90%",
        "50% against 90%",
        "no boss found",
        "80%; too few references",
    )
    assert table.caption == (
        "Share of 200s of enemy-alive time, summed over every enemy measured, that carried "
        "each debuff from this player or their pets, against the median of the parses that "
        "applied each. The verdict reads Overall, and Range and Sample are Overall's. Trash "
        "is the mobs of trash pulls; Bosses is the bosses themselves, a council's each from "
        "the pull's start to their own death, or to the pull's end if they did not die "
        "there; adds that spawn during a boss fight, and the enemies of a pull with no boss "
        "found, count in Overall only. Those columns and each boss's read ours against the "
        "median and carry no verdict. A debuff a teammate's application replaces is marked "
        "shared, not judged. The group's log for the whole fight held 1 removal with no "
        "application, dropped (a pet copy's second removal counts here); 2 applications "
        "still open at the fight's end, closed there; and 0 rows on an enemy with no game "
        "id, skipped. Derived."
    )
    # This row sets no reach, so every reach cell is empty, Range and Sample too.
    [unreached] = card.comparison_tables[2].rows
    assert unreached.cells == ("", "", "", "", "")


def a_shared_debuff_table(*shared_with: int, deathless: int = 0) -> ComparisonTable:
    """The debuff table of a card whose one row a teammate's application replaced."""
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=115804, name="Mortal Wounds", ours=0.7,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        trash=StretchCell(withheld=Withheld.NO_TRASH),
                        bosses=StretchCell(ours=0.7, their_median=0.9),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.7,
                                their_median=0.9,
                            ),
                        ),
                        shared_with=shared_with,
                    ),
                ),
                seconds=100.0,
                bosses=("First Boss",),
                tally=PairingTally(),
                deathless=deathless,
            ),
        )
    }
    loaded = a_loaded(
        players=(
            a_player(),
            Player(
                actor_id=2, name="Emberkin", class_name="Monk", spec="Windwalker",
                item_level=680,
            ),
            Player(
                actor_id=3, name="Bríala", class_name="DeathKnight", spec="Frost",
                item_level=680,
            ),
            Player(
                actor_id=4, name="Кириллица", class_name="Monk", spec="Windwalker",
                item_level=680,
            ),
        )
    )
    card = build_players(
        loaded, (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]
    coverage, _reach = card.comparison_tables
    return coverage


@pytest.mark.parametrize(
    ("deathless", "stated"),
    [
        (0, None),
        (1, "1 council boss of a kill pull had no death in the log and was measured to the "
            "pull's end."),
        (2, "2 council bosses of a kill pull had no death in the log and were measured to "
            "the pull's end."),
    ],
)
def test_a_council_boss_with_no_death_is_stated_only_when_there_is_one(
    deathless: int, stated: str | None
) -> None:
    caption = a_shared_debuff_table(deathless=deathless).caption

    if stated is None:
        assert "had no death" not in caption
    else:
        assert caption.endswith(f"skipped. {stated} Derived.")


def test_a_shared_debuff_is_labelled_with_who_it_was_shared_with_and_not_judged() -> None:
    [row] = a_shared_debuff_table(2).rows

    assert row.verdict_label == "Shared with Windwalker Monk"
    # The tint of a row that declined to judge: a shared row says nothing about
    # this player's play either, so it recedes as `unjudged` does.
    assert row.verdict == Verdict.UNJUDGED.value
    # The figures still show.
    assert row.cells == (
        "70% against 90%",
        "85% to 95%",
        "3 top parses",
        "no trash measured",
        "70% against 90%",
        "70% against 90%",
    )


def test_a_debuff_shared_with_two_teammates_names_both_by_spec_and_class() -> None:
    [row] = a_shared_debuff_table(2, 3).rows

    assert row.verdict_label == "Shared with Windwalker Monk and Frost Death Knight"


def test_teammates_of_one_spec_and_class_are_counted_not_repeated() -> None:
    # Two Windwalker Monks and a Death Knight: repeating the Monk would read as
    # a stutter and hide that two players held the slot.
    [row] = a_shared_debuff_table(2, 3, 4).rows

    assert row.verdict_label == "Shared with 2 Windwalker Monks and Frost Death Knight"


def test_an_unshared_debuff_keeps_its_own_verdict() -> None:
    [row] = a_shared_debuff_table().rows

    assert (row.verdict, row.verdict_label) == ("below", "Below")


def test_a_boss_no_reference_measured_is_labelled_for_what_the_cell_can_know() -> None:
    # A reference can have fought the boss and had it withheld, so the cell may
    # not claim that none reached it: it says only that none measured it.
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.7,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.9,
                                withheld=Withheld.NOT_REACHED,
                            ),
                        ),
                    ),
                ),
                seconds=100.0,
                bosses=("First Boss",),
                tally=PairingTally(),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [row] = card.comparison_tables[0].rows
    assert row.cells == (
        "70% against 90%", "85% to 95%", "3 top parses", "", "", "90%; no reference measured it"
    )
    assert BossCell(
        encounter_id=2001, boss="First Boss", withheld=Withheld.NOT_REACHED
    ).model_dump(mode="json")["withheld"] == "no reference measured this boss"


def test_the_buff_table_reads_overall_its_range_and_sample_then_each_stretch() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    ),
                    without_bosses=StretchCell(ours=0.55, their_median=0.97),
                    bosses=StretchCell(ours=0.9, withheld=Withheld.TOO_FEW),
                ),
            ),
            key_seconds=1834.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [table] = card.comparison_tables
    assert table.heading == "Buff uptime"
    assert (table.figures, table.judged) == (False, True)
    assert table.cell_headings == ("Overall", "Range", "Sample", "Without bosses", "Bosses")
    [row] = table.rows
    assert row.verdict_label == "Below"
    # Range and Sample are the references behind Overall's median, 95% to 99%
    # over three; neither stretch carries a range of its own.
    assert row.cells == (
        "62% against 98%",
        "95% to 99%",
        "3 top parses",
        "55% against 97%",
        "90%; too few references",
    )


def test_a_key_with_no_time_outside_its_boss_pulls_says_so_in_without_bosses() -> None:
    # The buff stretch is the key less its boss pulls, walking included, so an
    # empty cell there must not borrow the debuff's "no trash measured".
    measures = {
        "stonewake-0": PlayerMeasures(
            auras=(
                AuraRow(
                    uptime=AuraUptime(
                        ability_id=195181, name="Bone Shield", ours=0.62,
                        their_median=0.98, their_fractions=(0.95, 0.98, 0.99),
                        verdict=Verdict.BELOW,
                    ),
                    without_bosses=StretchCell(withheld=Withheld.NOTHING_OUTSIDE_BOSSES),
                    bosses=StretchCell(ours=0.62, their_median=0.98),
                ),
            ),
            key_seconds=1834.0,
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [table] = card.comparison_tables
    [row] = table.rows
    assert row.cells == (
        "62% against 98%",
        "95% to 99%",
        "3 top parses",
        "nothing outside boss pulls",
        "62% against 98%",
    )


def debuff_tables(
    *, unmeasured_no_death: int = 0, undebuffed_deaths: int = 0
) -> tuple[ComparisonTable, ComparisonTable]:
    """The coverage and reach tables of a card with one debuff, on one boss and on trash."""
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.6,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        trash=StretchCell(ours=0.4, their_median=0.85),
                        bosses=StretchCell(ours=0.95, their_median=0.97),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.95,
                                their_median=0.97,
                            ),
                        ),
                        reach=DebuffReach(
                            overall=StretchCell(ours=0.5, their_median=0.92),
                            trash=StretchCell(ours=0.45, their_median=0.9),
                            bosses=StretchCell(ours=1.0, their_median=1.0),
                            # Four, where the coverage row has three, and another
                            # range, so a reach Range or Sample read off the
                            # coverage figure would show.
                            overall_fractions=(0.88, 0.9, 0.94, 0.95),
                        ),
                    ),
                ),
                seconds=300.0,
                bosses=("First Boss",),
                tally=PairingTally(),
                unmeasured_no_death=unmeasured_no_death,
                undebuffed_deaths=undebuffed_deaths,
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]
    coverage, reach = card.comparison_tables
    return coverage, reach


def test_the_reach_table_follows_the_coverage_table_and_judges_nothing() -> None:
    coverage, reach = debuff_tables()

    assert (coverage.heading, reach.heading) == ("Debuff coverage", "Debuff reach")
    [covered] = coverage.rows
    assert covered.cells == (
        "60% against 90%",
        "85% to 95%",
        "3 top parses",
        "40% against 85%",
        "95% against 97%",
        "95% against 97%",
    )
    assert (reach.figures, reach.judged) == (False, False)
    assert reach.cell_headings == ("Overall", "Range", "Sample", "Trash", "Bosses")
    [row] = reach.rows
    assert (row.name, row.verdict, row.verdict_label) == ("Blood Plague", "described", "")
    # Range and Sample are the references' Overall reach, not their coverage.
    assert row.cells == (
        "50% against 92%",
        "88% to 95%",
        "4 top parses",
        "45% against 90%",
        "100% against 100%",
    )
    assert reach.caption == (
        "Share of the enemies measured that carried each debuff from this player or their "
        "pets at least once, against the median of the parses that applied each. Range and "
        "Sample are Overall's. A boss counts as one enemy. Reach describes and is never "
        "judged. Derived."
    )


def test_the_note_under_the_debuff_tables_explains_coverage_and_reach() -> None:
    coverage, reach = debuff_tables()

    assert coverage.note == ""
    assert reach.note == (
        "Coverage: the share of the enemies' alive time this player's debuff was on them, "
        "summed over every enemy, so a long-lived mob weighs more than one that dies in "
        "seconds. Reached: the share of the enemies that carried it at least once. Low "
        "coverage with high reach means it was spread but not kept up; low coverage with low "
        "reach means it stayed on too few mobs. A trash mob's life runs from the first debuff "
        "anyone put on it to its death; adds that spawn during a boss fight count in Overall "
        "only."
    )


@pytest.mark.parametrize(
    ("unmeasured", "undebuffed", "warning"),
    [
        (0, 0, ""),
        (3, 0, "3 enemies had no death in the log and were not measured."),
        (0, 1, "1 enemy died without anyone debuffing it and counts only toward reached."),
        (
            1,
            2,
            "1 enemy had no death in the log and was not measured; 2 died without anyone "
            "debuffing them and count only toward reached.",
        ),
    ],
)
def test_the_warning_states_each_count_only_when_above_zero(
    unmeasured: int, undebuffed: int, warning: str
) -> None:
    coverage, reach = debuff_tables(
        unmeasured_no_death=unmeasured, undebuffed_deaths=undebuffed
    )

    assert coverage.warning == ""
    assert reach.warning == warning


KEPT_SENTENCE = (
    "Not judged: the references keep it on under 10% of the key's enemy-alive time, so the "
    "row is kept for its boss figure."
)


def a_card_with_a_kept_debuff() -> tuple[ComparisonTable, ComparisonTable]:
    """The coverage and reach tables of a card with one judged debuff and one kept for bosses.

    The kept row's own figure is the higher of the two, so only its verdict can
    put it second.
    """
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=210824, name="Touch of the Magi", ours=0.05,
                            their_median=0.045, their_fractions=(0.04, 0.045, 0.05),
                            verdict=Verdict.BOSSES_ONLY,
                        ),
                        trash=StretchCell(withheld=Withheld.NO_TRASH),
                        bosses=StretchCell(ours=0.3, their_median=0.5),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.3,
                                their_median=0.5,
                            ),
                        ),
                        reach=DebuffReach(overall=StretchCell(ours=0.2, their_median=0.2)),
                    ),
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.04,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        reach=DebuffReach(overall=StretchCell(ours=0.5, their_median=0.9)),
                    ),
                ),
                seconds=300.0,
                bosses=("First Boss",),
                tally=PairingTally(),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]
    coverage, reach = card.comparison_tables
    return coverage, reach


def test_a_debuff_kept_for_its_boss_figure_reads_not_judged_and_sorts_after_the_judged() -> None:
    coverage, _reach = a_card_with_a_kept_debuff()

    judged, kept = coverage.rows
    assert (judged.name, judged.verdict_label) == ("Blood Plague", "Below")
    assert (kept.name, kept.verdict_label) == ("Touch of the Magi", "Not judged")
    # Its own state in the class, which the stylesheet greys as it does an
    # unjudged row; the word is the same because the reader's reading is.
    assert kept.verdict == Verdict.BOSSES_ONLY.value
    # Its Overall cell states ours and the median; its Bosses cells are drawn.
    assert kept.cells == (
        "5% against 4%",
        "4% to 5%",
        "3 top parses",
        "no trash measured",
        "30% against 50%",
        "30% against 50%",
    )


def test_the_reach_table_keeps_the_coverage_tables_order() -> None:
    _coverage, reach = a_card_with_a_kept_debuff()

    assert [row.name for row in reach.rows] == ["Blood Plague", "Touch of the Magi"]


def test_the_coverage_table_says_what_a_kept_row_is() -> None:
    coverage, reach = a_card_with_a_kept_debuff()

    assert coverage.note == KEPT_SENTENCE
    assert KEPT_SENTENCE not in reach.note


def test_a_table_with_no_kept_row_says_nothing_of_it() -> None:
    coverage, _reach = debuff_tables()

    assert coverage.note == ""


def test_a_stretch_every_reference_measured_and_none_applied_it_in_says_so_on_the_page() -> None:
    measures = {
        "stonewake-0": PlayerMeasures(
            debuffs=DebuffTable(
                rows=(
                    DebuffRow(
                        uptime=AuraUptime(
                            ability_id=55078, name="Blood Plague", ours=0.7,
                            their_median=0.9, their_fractions=(0.85, 0.9, 0.95),
                            verdict=Verdict.BELOW,
                        ),
                        bosses=StretchCell(ours=0.0, withheld=Withheld.NOT_APPLIED),
                        cells=(
                            BossCell(
                                encounter_id=2001, boss="First Boss", ours=0.4,
                                withheld=Withheld.NOT_APPLIED,
                            ),
                        ),
                    ),
                ),
                seconds=100.0,
                bosses=("First Boss",),
                tally=PairingTally(),
            ),
        )
    }
    card = build_players(
        a_loaded(), (), frozenset({"stonewake-0"}), a_player(), {},
        Defensives(), ThroughputCooldowns(), measures=measures,
    )[0]

    [row] = card.comparison_tables[0].rows
    assert row.cells[4:] == ("0%; no reference applied it", "40%; no reference applied it")

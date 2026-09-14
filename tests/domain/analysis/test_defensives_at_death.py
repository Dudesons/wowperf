# ABOUTME: The rule deciding which defensives a player had off cooldown when they died.
# ABOUTME: Every uncertainty in it is resolved toward silence, and these pin that direction.

from wowperf.domain.analysis.defensives import (
    analyse_defensives_at_death,
    defensives_up_at,
)
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import DefensiveAbility, Defensives

ICE_BLOCK = DefensiveAbility(ability_id=45438, name="Ice Block", cooldown_seconds=240.0)
BARRIER = DefensiveAbility(ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0)
ABILITIES = (ICE_BLOCK, BARRIER)

DEATH_MS = 300_000
"""Every case below is read against one death at this timestamp.

Ice Block's window is (240 + 10) seconds, so it opens at 50_000; Prismatic
Barrier's is (25 + 10), so it opens at 265_000.
"""


def a_cast(ability: DefensiveAbility, at_ms: int, actor_id: int = 11) -> CastEvent:
    return CastEvent(
        actor_id=actor_id, ability_id=ability.ability_id, ability_name=ability.name,
        timestamp_ms=at_ms,
    )


def owns_both(actor_id: int = 11) -> tuple[CastEvent, ...]:
    """One early cast of each, far outside every window: proof the player has them."""
    return (a_cast(ICE_BLOCK, 1_000, actor_id), a_cast(BARRIER, 1_000, actor_id))


def test_an_ability_the_player_never_cast_is_not_claimed_as_available() -> None:
    # Several abilities in the data file are talent-gated. A player who did not
    # take the talent casts it nowhere, which is indistinguishable from having it
    # and never pressing it. Claiming it was "available" would accuse someone of
    # not pressing a button they do not have.
    assert defensives_up_at((), ABILITIES, 11, DEATH_MS) == ()


def test_an_ability_cast_before_its_window_opened_was_available() -> None:
    casts = (a_cast(ICE_BLOCK, 49_000), a_cast(BARRIER, 1_000))
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS)


def test_a_cast_on_the_boundary_counts_against_availability() -> None:
    # The window is closed at its lower edge on purpose. An ability coming off
    # cooldown at the very instant the killing damage began is the most doubtful
    # case there is, and doubt here resolves to saying nothing.
    casts = (a_cast(ICE_BLOCK, 50_000),)
    assert "Ice Block" not in defensives_up_at(casts, ABILITIES, 11, DEATH_MS)


def test_an_ability_still_on_cooldown_was_not_available() -> None:
    casts = (a_cast(ICE_BLOCK, 51_000), a_cast(BARRIER, 1_000))
    assert defensives_up_at(casts, ABILITIES, 11, DEATH_MS) == ("Prismatic Barrier",)


def test_an_ability_pressed_during_the_run_up_is_not_called_unused() -> None:
    # They did press it and died anyway. The window covers the run-up precisely
    # so that this case never reads as neglect.
    casts = (a_cast(ICE_BLOCK, 1_000), a_cast(BARRIER, 295_000))
    assert "Prismatic Barrier" not in defensives_up_at(casts, ABILITIES, 11, DEATH_MS)


def test_a_cast_after_the_death_still_proves_the_player_has_the_ability() -> None:
    casts = (a_cast(ICE_BLOCK, 301_000),)
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS)


def test_charges_are_ignored_so_a_second_charge_reads_as_unavailable() -> None:
    # Stated as a test so nobody later reads this as a bug: a two-charge ability
    # cast once may well have had its second charge up, and this rule says it did
    # not. Understating availability cannot produce a false accusation.
    two_charges = DefensiveAbility(
        ability_id=108271, name="Astral Shift", cooldown_seconds=90.0, charges=2
    )
    casts = (a_cast(two_charges, 290_000),)
    assert defensives_up_at(casts, (two_charges,), 11, DEATH_MS) == ()


def test_only_this_players_casts_count() -> None:
    # Ours proves ownership early; theirs would have blocked the window had the
    # rule read the whole roster's casts.
    casts = owns_both() + (a_cast(ICE_BLOCK, 290_000, actor_id=12),)
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS)


def test_the_order_follows_the_ability_list() -> None:
    assert defensives_up_at(owns_both(), (BARRIER, ICE_BLOCK), 11, DEATH_MS) == (
        "Prismatic Barrier",
        "Ice Block",
    )


DEFENSIVES = Defensives(entries=(("Mage/Arcane", ABILITIES),))


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=400_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=318),
        ),
        pulls=pulls,
    )


def a_death(actor_id: int = 11, at_ms: int = DEATH_MS, name: str = "Emberkin") -> Death:
    return Death(
        player_name=name, actor_id=actor_id, timestamp_ms=at_ms,
        killing_blow="Shadow Bolt", pull_index=0, seconds_until_next_action=4.0,
    )


def test_a_death_with_a_defensive_available_is_a_finding() -> None:
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, run.pulls, owns_both(), DEFENSIVES, (a_death(),)
    )
    assert len(findings) == 1
    assert findings[0].id == "defensives.unused.emberkin"
    assert findings[0].confidence is Confidence.INFERRED
    # No honest number of seconds attaches to a button not pressed.
    assert findings[0].seconds_lost is None


def test_a_death_with_nothing_available_says_nothing() -> None:
    casts = owns_both() + (a_cast(ICE_BLOCK, 290_000), a_cast(BARRIER, 290_000))
    run = a_run()
    assert analyse_defensives_at_death(
        run.players, run.pulls, casts, DEFENSIVES, (a_death(),)
    ) == []


def test_a_player_who_cast_none_of_their_defensives_says_nothing_here() -> None:
    # The never-cast case belongs to the other analyser, which discloses that a
    # missing talent explains it just as well as a missing button press.
    run = a_run()
    assert analyse_defensives_at_death(run.players, run.pulls, (), DEFENSIVES, (a_death(),)) == []


def test_a_spec_the_data_file_does_not_cover_says_nothing() -> None:
    empty = Defensives(entries=())
    run = a_run()
    assert analyse_defensives_at_death(
        run.players, run.pulls, owns_both(), empty, (a_death(),)
    ) == []


def test_a_player_who_did_not_die_says_nothing() -> None:
    run = a_run()
    assert analyse_defensives_at_death(run.players, run.pulls, owns_both(), DEFENSIVES, ()) == []


def test_the_title_counts_only_the_deaths_that_qualified() -> None:
    # The first death has Ice Block up. By the second, Ice Block has been cast
    # and Barrier is inside its own window, so nothing was available.
    casts = owns_both() + (a_cast(BARRIER, 280_000), a_cast(ICE_BLOCK, 305_000))
    deaths = (a_death(at_ms=300_000), a_death(at_ms=310_000))
    run = a_run()
    findings = analyse_defensives_at_death(run.players, run.pulls, casts, DEFENSIVES, deaths)
    assert "once" in findings[0].title


def test_the_pull_index_comes_from_the_first_qualifying_death() -> None:
    # Nothing is up at the earlier death; Barrier has come back round by the later one.
    casts = owns_both() + (a_cast(BARRIER, 280_000), a_cast(ICE_BLOCK, 305_000))
    early = a_death(at_ms=310_000).model_copy(update={"pull_index": 7})
    late = a_death(at_ms=380_000).model_copy(update={"pull_index": 9})
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, run.pulls, casts, DEFENSIVES, (early, late)
    )
    assert findings[0].pull_index == 9


def test_the_evidence_names_the_killing_blow_and_what_was_up() -> None:
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, run.pulls, owns_both(), DEFENSIVES, (a_death(),)
    )
    # The class and spec lead, as they do in this module's other findings, so a
    # reader can discount the claim on sight. The death lines follow.
    assert findings[0].evidence[0] == "Mage Arcane"
    death_line = findings[0].evidence[1]
    assert "Shadow Bolt" in death_line
    assert "Ice Block" in death_line


def test_players_sharing_a_name_get_ids_that_tell_them_apart() -> None:
    run = a_run()
    run = run.model_copy(
        update={
            "players": run.players
            + (Player(actor_id=12, name="Emberkin", class_name="Mage", spec="Arcane",
                      item_level=300),)
        }
    )
    casts = owns_both(11) + owns_both(12)
    deaths = (a_death(actor_id=11), a_death(actor_id=12))
    ids = {
        finding.id
        for finding in analyse_defensives_at_death(
            run.players, run.pulls, casts, DEFENSIVES, deaths
        )
    }
    assert ids == {"defensives.unused.emberkin.11", "defensives.unused.emberkin.12"}


def test_players_whose_names_slug_alike_get_ids_that_tell_them_apart() -> None:
    """The name guard never fires here, because these two do not share a name.

    `Bríala` and `Briala` share only a slug, and the slug is what the id
    carries. Disambiguation therefore has to count slugs; counting names
    would leave both deaths addressing one element on the page.
    """
    run = a_run()
    mage = run.players[0]
    run = run.model_copy(update={
        "players": (
            mage.model_copy(update={"name": "Bríala"}),
            mage.model_copy(update={"actor_id": 12, "name": "Briala"}),
        ),
    })
    casts = owns_both(11) + owns_both(12)
    deaths = (a_death(actor_id=11), a_death(actor_id=12))

    ids = {
        finding.id
        for finding in analyse_defensives_at_death(
            run.players, run.pulls, casts, DEFENSIVES, deaths
        )
    }

    assert ids == {"defensives.unused.briala.11", "defensives.unused.briala.12"}

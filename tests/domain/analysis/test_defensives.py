# ABOUTME: Behaviour tests for the defensive claims a combat log can support.
# ABOUTME: Pressed far below the cooldown ceiling is a caveated claim; the ceiling is a bound.

from wowperf.domain.analysis.defensives import (
    _ceiling_withheld,
    alive_combat_seconds,
    analyse_defensive_ceiling,
)
from wowperf.domain.events import CastEvent, Death
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import DefensiveAbility, Defensives

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(
                    ability_id=235450, name="Prismatic Barrier", cooldown_seconds=25.0
                ),
                DefensiveAbility(
                    ability_id=45438, name="Ice Block", cooldown_seconds=240.0
                ),
            ),
        ),
    )
)

BLOOD_DEFENSIVES = Defensives(
    entries=(
        (
            "DeathKnight/Blood",
            (
                DefensiveAbility(
                    ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0
                ),
            ),
        ),
    )
)

SHAPE = "run"
"""Every fixture here models a Mythic+ run, the noun `service.py` passes in production."""


def run_combat_description(seconds: float) -> str:
    """The phrase `service.py` builds for the withheld notice, reproduced for these fixtures.

    `analyse_defensive_ceiling` takes this as a caller-supplied string precisely
    so the analyser itself never decides how to phrase `combat_seconds` --
    see its own docstring and `_ceiling_withheld`'s.
    """
    return f"This run's pulls summed to {seconds:.0f}s of combat"


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=100_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
    )


def a_long_run() -> Run:
    """`a_run()` stretched to 1800s, which is what makes a ceiling finding possible.

    At `a_run()`'s 100 seconds Prismatic Barrier's ceiling is 4.0 and a single
    press clears the 0.2 fraction, so no ceiling finding fires for any input.
    At 1800 seconds the two ceilings are 72.0 and 7.5, and one press of each
    sits far below both. Tests that pin id shape, slugging or independence use
    this fixture so that what they assert about is a claim the analyser can
    actually make.
    """
    base = a_run()
    return base.model_copy(
        update={"pulls": (base.pulls[0].model_copy(update={"end_ms": 1_800_000}),)}
    )


def ceiling_ids(findings: list[Finding]) -> list[str]:
    """Ids of the ceiling findings only, sorted.

    Scoped rather than taking every finding, so that an assertion about the
    ceiling family cannot be satisfied — or broken — by a neighbouring family.
    """
    return sorted(
        finding.id for finding in findings if finding.id.startswith("defensives.ceiling.")
    )


def cast(actor_id: int, ability_id: int) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=1_000, pull_index=0)


def a_run_with_one_blood_death_knight(pull_seconds: float) -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0,
             end_ms=int(pull_seconds * 1000), killed=True, x=10, y=20,
             enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=1, name="Tank", class_name="DeathKnight", spec="Blood",
                   item_level=320),
        ),
        pulls=pulls,
    )


def a_cast(actor_id: int, ability_id: int) -> CastEvent:
    return CastEvent(actor_id=actor_id, ability_id=ability_id, ability_name="x",
                     timestamp_ms=1_000, pull_index=0)


def findings_by_prefix(findings: list[Finding], prefix: str) -> list[Finding]:
    return [finding for finding in findings if finding.id.startswith(prefix)]


def test_a_spec_absent_from_the_list_produces_nothing() -> None:
    # Sublime is an Elemental Shaman and the fixture only knows Arcane Mages.
    # Anchored on casts that do produce findings for the Mage, so the Shaman's
    # absence is this analyser declining to judge an unlisted spec rather than
    # the call having produced nothing for anybody. Sublime presses the Mage's
    # two abilities as well, because the ceiling branch needs at least one cast
    # to reach a title: without them a `for_spec` that wrongly matched an
    # unlisted spec would still mint no Shaman row and the assertion would hold.
    run = a_long_run()
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds,
        (cast(11, 235450), cast(11, 45438), cast(12, 235450), cast(12, 45438)),
        DEFENSIVES, (), combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert ceiling_ids(findings)
    assert all("Sublime" not in finding.title for finding in findings)


def test_a_cast_outside_every_pull_still_counts_as_used() -> None:
    # pull_index=None means the cast landed outside any pull window (e.g.
    # between packs). The player still pressed the button, so it counts towards
    # the ceiling: a ceiling finding for Ice Block can only exist if the press
    # was counted, because an ability with zero uses reaches no ceiling at all.
    outside_pull = CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                             timestamp_ms=1_000, pull_index=None)
    run = a_long_run()
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (cast(11, 235450), outside_pull), DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert "defensives.ceiling.emberkin.45438" in ceiling_ids(findings)


def test_two_players_of_the_same_spec_are_reported_independently() -> None:
    # Two Arcane mages, each pressing both listed defensives once. Each must get
    # their own pair of rows: one player's presses must not answer for the other.
    run = a_long_run()
    other_mage = Player(actor_id=13, name="Othermage", class_name="Mage", spec="Arcane",
                        item_level=300)
    run = run.model_copy(update={"players": run.players + (other_mage,)})
    casts = (cast(11, 235450), cast(11, 45438), cast(13, 235450), cast(13, 45438))
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert ceiling_ids(findings) == [
        "defensives.ceiling.emberkin.235450",
        "defensives.ceiling.emberkin.45438",
        "defensives.ceiling.othermage.235450",
        "defensives.ceiling.othermage.45438",
    ]


def test_same_named_players_get_distinct_finding_ids() -> None:
    run = a_long_run()
    twin = Player(actor_id=99, name="Emberkin", class_name="Mage", spec="Arcane",
                  item_level=300)
    run = run.model_copy(update={"players": run.players + (twin,)})
    casts = (cast(11, 235450), cast(11, 45438), cast(99, 235450), cast(99, 45438))
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    ids = ceiling_ids(findings)
    # Counted, not just deduplicated: `len(ids) == len(set(ids))` holds for an
    # empty list, so it cannot tell a working disambiguation from no findings.
    assert len(ids) == 4, ids
    assert len(set(ids)) == len(ids), ids


def test_defensives_with_no_entries_produces_nothing() -> None:
    # Cast the abilities the populated file lists, so that emptiness here is
    # caused by the empty defensives file and not by an input nobody pressed.
    run = a_long_run()
    casts = (cast(11, 235450), cast(11, 45438))
    assert ceiling_ids(analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    ))
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, Defensives(entries=()), (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert findings == []


def a_death(actor_id: int, seconds: float | None) -> Death:
    return Death(
        player_name="Tank",
        actor_id=actor_id,
        timestamp_ms=0,
        killing_blow="Something",
        seconds_until_next_action=seconds,
    )


def test_alive_seconds_subtracts_dead_time_from_the_combat_denominator() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              killing_blow="Melee", seconds_until_next_action=12.0, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11, combat_end_ms=100_000) == 88.0


def test_a_death_with_no_following_action_counts_as_dead_until_combat_end() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              killing_blow="Melee", seconds_until_next_action=None, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11, combat_end_ms=100_000) == 50.0


def test_a_death_never_followed_by_an_action_counts_as_dead_until_combat_ended() -> None:
    # Combat ran to 300_000ms. This player died at 200_000 and never acted on
    # another actor again, so the fight ended with them dead: they were alive
    # for 200s of the 300s and dead for the last 100. Exact, not estimated --
    # a fight that ended at that death is a fight they provably never rejoined.
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=200_000,
              killing_blow="Something", seconds_until_next_action=None),
    )

    assert alive_combat_seconds(300.0, deaths, 11, combat_end_ms=300_000) == 200.0


def test_a_player_who_only_self_buffed_after_dying_has_their_alive_time_understated() -> None:
    # `seconds_until_next_action` is None for a resurrected player whose only
    # later casts are on themselves -- ingest counts a cast at another actor and
    # nothing else. Treating them as dead to the end understates how long they
    # were alive, which lowers their ceiling and makes the claim weaker. That is
    # the direction this module leans everywhere, and this pins it: 300s of
    # combat, dead at 100_000ms, credited with 100s alive rather than more.
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=100_000,
              killing_blow="Something", seconds_until_next_action=None),
    )

    assert alive_combat_seconds(300.0, deaths, 11, combat_end_ms=300_000) == 100.0


def test_alive_seconds_never_goes_negative() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              killing_blow="Melee", seconds_until_next_action=500.0, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11, combat_end_ms=100_000) == 0.0


def test_a_fight_with_no_pulls_still_has_a_ceiling_denominator() -> None:
    """The defect this narrowing exists to remove.

    Passing `run.total_pull_seconds` for a raid fight passes zero, and every
    ceiling finding disappears without a word. Passing fight duration does not.
    """
    assert alive_combat_seconds(374.0, (), 11, combat_end_ms=374_000) == 374.0


def test_a_defensive_pressed_far_below_its_ceiling_is_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "1 of" in ceiling[0].title
    assert ceiling[0].confidence is Confidence.INFERRED
    assert ceiling[0].seconds_lost is None


def test_a_defensive_never_pressed_produces_no_ceiling_finding() -> None:
    # Paired against the pressed case on purpose. With no casts at all the
    # result is empty for every reason at once, so an emptiness assertion on
    # its own would still pass if the ceiling branch stopped working entirely.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)

    pressed = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (a_cast(actor_id=1, ability_id=48792),),
        BLOOD_DEFENSIVES, (), combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert findings_by_prefix(pressed, "defensives.ceiling.") != []

    unpressed = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (), BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert findings_by_prefix(unpressed, "defensives.ceiling.") == []


def test_a_defensive_pressed_at_roughly_half_its_ceiling_is_ordinary_play() -> None:
    # A whole-branch review ran this analyser against a realistic 28-minute run
    # and realistic press counts: seven of eight pressed defensives produced a
    # finding at the 0.5 threshold, because "used slightly under half of the
    # theoretical maximum" is what most defensives look like in ordinary play,
    # not neglect. Ceiling 10, 4 presses (40% of ceiling) must not be a story.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = tuple(a_cast(actor_id=1, ability_id=48792) for _ in range(4))

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_a_defensive_pressed_close_to_its_ceiling_is_not_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    # 1800s / 180s = a ceiling of 10; eight presses is not a story.
    casts = tuple(a_cast(actor_id=1, ability_id=48792) for _ in range(8))

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_a_run_too_short_for_a_meaningful_ceiling_reports_nothing() -> None:
    # The floor is the fraction's own arithmetic. A press count is a positive
    # integer, so `uses < ceiling * CEILING_USE_FRACTION` cannot hold until the
    # ceiling clears 1 / 0.2 = 5, whatever the press count.
    #
    # Anchored at both sides of that boundary on purpose: an emptiness
    # assertion alone would still pass if the ceiling branch stopped working
    # entirely, which is how a floor test comes to be incapable of failing.
    casts = (a_cast(actor_id=1, ability_id=48792),)

    # 900s / 180s = a ceiling of exactly 5, so the press needs 1 < 1.0. That is
    # also exactly where a fight is too short to judge at all, so this excludes
    # the withheld notice: what is asserted here is the per-ability judgment,
    # which the notice is not.
    at_the_floor = a_run_with_one_blood_death_knight(pull_seconds=900.0)
    silent = analyse_defensive_ceiling(
        at_the_floor.players, at_the_floor.total_pull_seconds, casts,
        BLOOD_DEFENSIVES, (), combat_end_ms=at_the_floor.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(at_the_floor.total_pull_seconds),
    )
    judged = [f for f in findings_by_prefix(silent, "defensives.ceiling.")
              if f.id != "defensives.ceiling.withheld"]
    assert judged == []

    # 1080s / 180s = a ceiling of 6, and the same single press needs 1 < 1.2.
    above_the_floor = a_run_with_one_blood_death_knight(pull_seconds=1080.0)
    reported = analyse_defensive_ceiling(
        above_the_floor.players, above_the_floor.total_pull_seconds, casts,
        BLOOD_DEFENSIVES, (), combat_end_ms=above_the_floor.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(above_the_floor.total_pull_seconds),
    )
    assert findings_by_prefix(reported, "defensives.ceiling.") != []


def test_a_run_with_no_pulls_mints_no_withheld_notice_even_with_a_pressed_defensive() -> None:
    # `Run.window_ms` and `total_pull_seconds` both collapse to zero with no
    # pulls at all (`model.py:152`). Without a guard on `combat_seconds > 0`,
    # `cooldown_ceiling(0, ability) == 0 <= 5` for any ability pressed outside
    # every pull window, and the withheld notice would mint blaming the run's
    # length -- false: nothing here says the run was short, only that the log
    # carried no pulls to time it by.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0).model_copy(
        update={"pulls": ()}
    )
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert findings == []


def test_time_spent_dead_does_not_count_towards_the_ceiling() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)
    # 720s of the 1800s were spent dead, so the ceiling falls from 10 to 6; one
    # press against a ceiling of 6 still clears the 0.2 threshold (1 < 1.2).
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (a_death(1, 720.0),),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "6 times" in ceiling[0].title, ceiling[0].title


def test_the_ceiling_detail_says_defensives_are_situational() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    finding = findings_by_prefix(
        analyse_defensive_ceiling(
            run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
            combat_end_ms=run.window_ms[1], shape=SHAPE,
            combat_description=run_combat_description(run.total_pull_seconds),
        ),
        "defensives.ceiling.",
    )[0]

    assert "incoming damage" in finding.detail


def test_a_player_dead_from_the_first_second_has_no_ceiling_to_judge() -> None:
    # a_death(..., None) times this death at 0ms, and seconds_until_next_action
    # of None means the player was never seen to act on another actor again --
    # so they count as dead from timestamp 0 to combat_end_ms, which is the
    # entire 1800s fight. Alive time clamps to zero and the ceiling is zero,
    # and `uses` for a pressed ability is always at least 1, so `1 >= 0 * 0.2`
    # holds and no per-ability finding fires for it either -- which is why the
    # fixture only needs to press the one ability it lists.
    #
    # Paired against the same call without that death, so the emptiness below
    # is this death's doing and not the analyser having failed wholesale.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    defensives = Defensives(
        entries=(
            (
                "DeathKnight/Blood",
                (
                    DefensiveAbility(
                        ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0
                    ),
                ),
            ),
        )
    )
    casts = (a_cast(actor_id=1, ability_id=48792),)

    measured = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, defensives, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    assert findings_by_prefix(measured, "defensives.ceiling.") != []

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, defensives, (a_death(1, None),),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert findings == []


def test_two_same_named_players_get_distinct_ceiling_finding_ids() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    twin = Player(actor_id=2, name="Tank", class_name="DeathKnight", spec="Blood",
                  item_level=320)
    run = run.model_copy(update={"players": run.players + (twin,)})
    casts = (
        a_cast(actor_id=1, ability_id=48792),
        a_cast(actor_id=2, ability_id=48792),
    )

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 2
    assert {finding.id for finding in ceiling} == {
        "defensives.ceiling.tank.1.48792",
        "defensives.ceiling.tank.2.48792",
    }


def test_a_ceiling_finding_names_the_defensive_it_judged() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (a_cast(actor_id=1, ability_id=48792),),
        BLOOD_DEFENSIVES, (), combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")[0]
    assert ceiling.ability_id == 48792
    assert ceiling.ability_name == "Icebound Fortitude"
    assert ceiling.ability_name in ceiling.title


def a_run_named(name: str) -> Run:
    """The Arcane mage of `a_run`, renamed, so only the name varies."""
    base = a_run()
    return base.model_copy(update={
        "players": (base.players[0].model_copy(update={"name": name}), base.players[1]),
    })


def test_a_defensive_finding_id_carries_no_character_outside_the_ascii_set() -> None:
    """Every finding id becomes an HTML element id, so it has to be addressable.

    `defensives.*` built its id from the raw display name while every
    `compare.*` family slugs it, which put a real player's name -- and, for a
    non-Latin one, characters no fragment should carry -- into the page's own
    element ids.
    """
    run = a_run_named("Кириллица")
    run = run.model_copy(
        update={"pulls": (run.pulls[0].model_copy(update={"end_ms": 1_800_000}),)}
    )
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (cast(11, 235450), cast(11, 45438)),
        DEFENSIVES, (), combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    ids = ceiling_ids(findings)
    # Anchored: this player presses both listed defensives well below their
    # ceilings, so rows must exist for the assertion below to mean anything.
    assert ids
    for finding_id in ids:
        assert finding_id.isascii(), finding_id


def test_two_names_that_slug_alike_still_reach_different_defensive_finding_ids() -> None:
    """Slugging discards information, so it must not discard the distinction.

    `Bríala` and `Briala` are two different players and reduce to one slug.
    The id appends the actor id when two players share a *name*, and these two
    do not, so that guard never fires -- the disambiguation has to key on what
    the id actually carries, which after this change is the slug.
    """
    base = a_long_run()
    mage = base.players[0]
    run = base.model_copy(update={
        "players": (
            mage.model_copy(update={"name": "Bríala"}),
            mage.model_copy(update={"actor_id": 12, "name": "Briala"}),
        ),
    })
    casts = (cast(11, 235450), cast(11, 45438), cast(12, 235450), cast(12, 45438))

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    ids = ceiling_ids(findings)
    assert len(ids) == 4, ids
    assert len(set(ids)) == len(ids), ids


def test_a_uniquely_named_player_gets_an_id_with_no_actor_number_in_it() -> None:
    """The actor id is the disambiguator, and it appears only when needed.

    Pinned exactly rather than by prefix: `defensives.ceiling.emberkin.45438`
    and `defensives.ceiling.emberkin.11.45438` share a prefix, so a prefix
    assertion cannot tell a working disambiguation from one that fires for
    everybody.
    """
    run = a_long_run()
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (cast(11, 235450), cast(11, 45438)),
        DEFENSIVES, (), combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert set(ceiling_ids(findings)) == {
        "defensives.ceiling.emberkin.235450",
        "defensives.ceiling.emberkin.45438",
    }


def test_a_fight_too_short_for_a_pressed_defensive_says_so() -> None:
    # Icebound Fortitude's 180s cooldown means a single press cannot clear the
    # withheld notice's own threshold -- escape being flagged as too-short-to-
    # judge -- until combat exceeds 900s: at exactly 900s the ceiling is 5 and
    # `uses < ceiling * 0.2` (1 < 1.0) is still true, so the notice still
    # fires. This run is 600s, so the analyser cannot judge it at all -- and
    # silence about it would read exactly like having pressed it enough.
    run = a_run_with_one_blood_death_knight(pull_seconds=600.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    withheld = [f for f in findings if f.id == "defensives.ceiling.withheld"]
    assert len(withheld) == 1, [f.id for f in findings]
    assert withheld[0].confidence is Confidence.MEASURED
    assert "Icebound Fortitude" in " ".join(withheld[0].evidence)


def test_an_ability_nobody_pressed_does_not_produce_a_withheld_notice() -> None:
    # Same 600s run, and Icebound Fortitude is still out of reach -- but nobody
    # pressed it, so there is nothing the analyser declined to judge. Minting a
    # notice from the cooldown table alone would put a line on every report.
    run = a_run_with_one_blood_death_knight(pull_seconds=600.0)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (), BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert [f for f in findings if f.id == "defensives.ceiling.withheld"] == []


def test_a_fight_long_enough_for_every_pressed_defensive_says_nothing() -> None:
    # 1080s fits Icebound Fortitude's 180s cooldown six times, clear of the
    # floor, so the ability is judgeable and there is nothing to withhold.
    run = a_run_with_one_blood_death_knight(pull_seconds=1080.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    assert [f for f in findings if f.id == "defensives.ceiling.withheld"] == []


def test_the_withheld_notice_accounts_for_a_players_charges() -> None:
    # Two charges halves how long combat must run before a press could ever
    # clear the threshold: 180s / 2 charges / 0.2 = 450s, not the 900s a
    # single-charge ability of the same cooldown needs. Pinning this figure
    # guards the `/ ability.charges` term the withheld notice reports.
    cooldown_seconds = 180.0
    two_charges = Defensives(
        entries=(
            ("DeathKnight/Blood", (
                DefensiveAbility(ability_id=48792, name="Icebound Fortitude",
                                  cooldown_seconds=cooldown_seconds, charges=2),
            )),
        )
    )
    run = a_run_with_one_blood_death_knight(pull_seconds=300.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, two_charges, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    withheld = [f for f in findings if f.id == "defensives.ceiling.withheld"][0]
    assert "Icebound Fortitude would need more than 450s of combat" in withheld.evidence
    # Unconditional, and tied to the fixture rather than to any wording: a
    # charge-blind reading of "five cooldowns" lands on this figure for this
    # ability, and the detail must never state it beside a 450s evidence line
    # -- one finding cannot carry two different thresholds for the same press.
    charge_blind_figure = f"{cooldown_seconds * 5:.0f}"
    assert charge_blind_figure not in withheld.detail, withheld.detail


def test_two_specs_whose_same_named_ability_differs_both_get_their_own_line() -> None:
    # Barkskin's cooldown is 45s for a Guardian and 60s for every other druid
    # spec (data/defensives.toml). A raid holding both must not have one
    # player's figure silently stand in for the other's.
    two_variants = Defensives(
        entries=(
            ("Druid/Guardian", (
                DefensiveAbility(ability_id=22812, name="Barkskin", cooldown_seconds=45.0),
            )),
            ("Druid/Balance", (
                DefensiveAbility(ability_id=22812, name="Barkskin", cooldown_seconds=60.0),
            )),
        )
    )
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0,
             end_ms=200_000, killed=True, x=10, y=20,
             enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    run = Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk", encounter_id=12825,
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=100, count_required=100, npc_counts=(),
        players=(
            Player(actor_id=1, name="Guardian", class_name="Druid", spec="Guardian",
                   item_level=320),
            Player(actor_id=2, name="Boomkin", class_name="Druid", spec="Balance",
                   item_level=320),
        ),
        pulls=pulls,
    )
    casts = (a_cast(actor_id=1, ability_id=22812), a_cast(actor_id=2, ability_id=22812))

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, two_variants, (),
        combat_end_ms=run.window_ms[1], shape=SHAPE,
        combat_description=run_combat_description(run.total_pull_seconds),
    )

    withheld = [f for f in findings if f.id == "defensives.ceiling.withheld"][0]
    assert "Barkskin would need more than 225s of combat" in withheld.evidence
    assert "Barkskin would need more than 300s of combat" in withheld.evidence
    # One ability, in two specs' variants -- a reader counting named
    # defensives sees one, and the title and detail must agree with them
    # rather than counting the two lines the evidence carries for it.
    assert withheld.title == "This run was too short to judge 1 pressed defensive"
    assert "1 of the defensives" in withheld.detail, withheld.detail


def test_the_withheld_notice_uses_the_callers_shape_and_combat_description() -> None:
    # `analyse_defensive_ceiling` no longer hard-codes "fight" or "ran Ns":
    # a keystone report says "run" throughout and a raid page says "fight",
    # and what `combat_seconds` honestly measures differs the same way --
    # summed pull time on a keystone, wall-clock duration on a raid. Both
    # come from the caller. Deliberately neither production value here --
    # "expedition" is not a shape this codebase ever passes, and the combat
    # description names a number `combat_seconds` itself is not (600.0) --
    # so a regression that silently reverted to hard-coding "fight" and
    # `f"This fight ran {combat_seconds:.0f}s"` could not satisfy this by
    # coincidence the way passing the real production words would risk.
    run = a_run_with_one_blood_death_knight(pull_seconds=600.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (),
        combat_end_ms=run.window_ms[1], shape="expedition",
        combat_description="This expedition logged 12345s on a wholly different clock",
    )

    withheld = [f for f in findings if f.id == "defensives.ceiling.withheld"][0]
    assert withheld.title == "This expedition was too short to judge 1 pressed defensive"
    assert "This expedition logged 12345s on a wholly different clock" in withheld.detail
    assert "into the expedition" in withheld.detail
    assert "fight" not in withheld.title
    assert "600" not in withheld.detail


def test_the_withheld_detail_and_evidence_read_as_one_paragraph_when_joined() -> None:
    """Critical 1 of the whole-branch review: the page appends `evidence` straight
    onto `detail` for the single Provenance entry a reader sees (`build.py`'s
    `ceiling_withheld_line`), so `detail` must end on a clause that leads into
    those lines rather than pointing at a section the page never had.
    """
    finding = _ceiling_withheld(
        {("Ice Block", 1200.0)}, shape="run",
        combat_description="This run's pulls summed to 300s of combat",
    )

    assert finding.detail.endswith("so each is named here:")
    joined = f"{finding.detail} " + "; ".join(finding.evidence) + "."
    assert "Ice Block would need more than 1200s of combat" in joined
    # The old wording promised a breakdown "stated per ability below" that no
    # template ever rendered -- nothing on this page is spatially below the
    # detail, since both live in the same paragraph.
    assert "per ability below" not in finding.detail

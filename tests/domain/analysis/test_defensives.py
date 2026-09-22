# ABOUTME: Behaviour tests for the defensive claims a combat log can support.
# ABOUTME: Pressed far below the cooldown ceiling is a caveated claim; the ceiling is a bound.

from wowperf.domain.analysis.defensives import alive_combat_seconds, analyse_defensive_ceiling
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
        DEFENSIVES, ()
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
        run.players, run.total_pull_seconds, (cast(11, 235450), outside_pull), DEFENSIVES, ()
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
    findings = analyse_defensive_ceiling(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())

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
    findings = analyse_defensive_ceiling(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())
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
        run.players, run.total_pull_seconds, casts, DEFENSIVES, ()
    ))
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, Defensives(entries=()), ()
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
    assert alive_combat_seconds(100.0, deaths, 11) == 88.0


def test_alive_seconds_is_unknown_when_a_death_was_never_followed_by_an_action() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              killing_blow="Melee", seconds_until_next_action=None, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11) is None


def test_alive_seconds_never_goes_negative() -> None:
    deaths = (
        Death(actor_id=11, player_name="Emberkin", timestamp_ms=50_000,
              killing_blow="Melee", seconds_until_next_action=500.0, pull_index=0),
    )
    assert alive_combat_seconds(100.0, deaths, 11) == 0.0


def test_a_fight_with_no_pulls_still_has_a_ceiling_denominator() -> None:
    """The defect this narrowing exists to remove.

    Passing `run.total_pull_seconds` for a raid fight passes zero, and every
    ceiling finding disappears without a word. Passing fight duration does not.
    """
    assert alive_combat_seconds(374.0, (), 11) == 374.0


def test_a_defensive_pressed_far_below_its_ceiling_is_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, ()
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
        BLOOD_DEFENSIVES, ()
    )
    assert findings_by_prefix(pressed, "defensives.ceiling.") != []

    unpressed = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, (), BLOOD_DEFENSIVES, ()
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
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, ()
    )

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_a_defensive_pressed_close_to_its_ceiling_is_not_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    # 1800s / 180s = a ceiling of 10; eight presses is not a story.
    casts = tuple(a_cast(actor_id=1, ability_id=48792) for _ in range(8))

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, ()
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

    # 900s / 180s = a ceiling of exactly 5, so the press needs 1 < 1.0.
    at_the_floor = a_run_with_one_blood_death_knight(pull_seconds=900.0)
    silent = analyse_defensive_ceiling(
        at_the_floor.players, at_the_floor.total_pull_seconds, casts,
        BLOOD_DEFENSIVES, ()
    )
    assert findings_by_prefix(silent, "defensives.ceiling.") == []

    # 1080s / 180s = a ceiling of 6, and the same single press needs 1 < 1.2.
    above_the_floor = a_run_with_one_blood_death_knight(pull_seconds=1080.0)
    reported = analyse_defensive_ceiling(
        above_the_floor.players, above_the_floor.total_pull_seconds, casts,
        BLOOD_DEFENSIVES, ()
    )
    assert findings_by_prefix(reported, "defensives.ceiling.") != []


def test_time_spent_dead_does_not_count_towards_the_ceiling() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)
    # 720s of the 1800s were spent dead, so the ceiling falls from 10 to 6; one
    # press against a ceiling of 6 still clears the 0.2 threshold (1 < 1.2).
    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, (a_death(1, 720.0),)
    )
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "6 times" in ceiling[0].title, ceiling[0].title


def test_the_ceiling_detail_says_defensives_are_situational() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    finding = findings_by_prefix(
        analyse_defensive_ceiling(
            run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, ()
        ),
        "defensives.ceiling.",
    )[0]

    assert "incoming damage" in finding.detail


def test_a_death_with_unmeasured_cost_disables_every_ceiling_for_that_player() -> None:
    # seconds_until_next_action=None means the player's last recorded action in
    # the run was dying, so there is no honest dead-time figure for them and
    # therefore no honest alive-time figure either. That must withhold every
    # ceiling finding for this player, not just the one for the ability they
    # actually pressed — which is why the fixture lists two defensives and
    # presses one.
    #
    # Paired against the same call without that death, so the emptiness below
    # is the unmeasured death doing the suppressing and not the analyser having
    # failed wholesale.
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    defensives = Defensives(
        entries=(
            (
                "DeathKnight/Blood",
                (
                    DefensiveAbility(
                        ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0
                    ),
                    DefensiveAbility(
                        ability_id=194679, name="Rune Tap", cooldown_seconds=30.0
                    ),
                ),
            ),
        )
    )
    casts = (a_cast(actor_id=1, ability_id=48792),)

    measured = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, defensives, ()
    )
    assert findings_by_prefix(measured, "defensives.ceiling.") != []

    findings = analyse_defensive_ceiling(
        run.players, run.total_pull_seconds, casts, defensives, (a_death(1, None),)
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
        run.players, run.total_pull_seconds, casts, BLOOD_DEFENSIVES, ()
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
        BLOOD_DEFENSIVES, ()
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
        DEFENSIVES, ()
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

    findings = analyse_defensive_ceiling(run.players, run.total_pull_seconds, casts, DEFENSIVES, ())

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
        DEFENSIVES, ()
    )

    assert set(ceiling_ids(findings)) == {
        "defensives.ceiling.emberkin.235450",
        "defensives.ceiling.emberkin.45438",
    }

# ABOUTME: The rule deciding which defensives a player had off cooldown when they died.
# ABOUTME: Every uncertainty in it is resolved toward silence, and these pin that direction.

from tests.domain.progression_fixtures import a_loaded_series
from tests.domain.test_progression import an_attempt
from wowperf.domain.analysis.deaths import pull_offset
from wowperf.domain.analysis.defensives import (
    analyse_defensives_at_death,
    defensives_up_at,
    repeat_defensives_up,
)
from wowperf.domain.encounter import LoadedEncounter
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

LOG_FROM = 0
"""The log's first second for every case not about that edge: both windows above open after it.

The cases about the edge itself pass their own origin.
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
    assert defensives_up_at((), ABILITIES, 11, DEATH_MS, visible_from_ms=LOG_FROM) == ()


def test_an_ability_cast_before_its_window_opened_was_available() -> None:
    casts = (a_cast(ICE_BLOCK, 49_000), a_cast(BARRIER, 1_000))
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS, visible_from_ms=LOG_FROM)


def test_a_cast_on_the_boundary_counts_against_availability() -> None:
    # The window is closed at its lower edge on purpose. An ability coming off
    # cooldown at the very instant the killing damage began is the most doubtful
    # case there is, and doubt here resolves to saying nothing.
    casts = (a_cast(ICE_BLOCK, 50_000),)
    assert "Ice Block" not in defensives_up_at(
        casts, ABILITIES, 11, DEATH_MS,
        visible_from_ms=LOG_FROM,
    )


def test_an_ability_still_on_cooldown_was_not_available() -> None:
    casts = (a_cast(ICE_BLOCK, 51_000), a_cast(BARRIER, 1_000))
    assert defensives_up_at(
        casts, ABILITIES, 11, DEATH_MS,
        visible_from_ms=LOG_FROM,
    ) == ("Prismatic Barrier",)


def test_an_ability_pressed_during_the_run_up_is_not_called_unused() -> None:
    # They did press it and died anyway. The window covers the run-up precisely
    # so that this case never reads as neglect.
    casts = (a_cast(ICE_BLOCK, 1_000), a_cast(BARRIER, 295_000))
    assert "Prismatic Barrier" not in defensives_up_at(
        casts, ABILITIES, 11, DEATH_MS,
        visible_from_ms=LOG_FROM,
    )


def test_a_cast_after_the_death_still_proves_the_player_has_the_ability() -> None:
    casts = (a_cast(ICE_BLOCK, 301_000),)
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS, visible_from_ms=LOG_FROM)


def test_charges_are_ignored_so_a_second_charge_reads_as_unavailable() -> None:
    # Stated as a test so nobody later reads this as a bug: a two-charge ability
    # cast once may well have had its second charge up, and this rule says it did
    # not. Understating availability cannot produce a false accusation.
    two_charges = DefensiveAbility(
        ability_id=108271, name="Astral Shift", cooldown_seconds=90.0, charges=2
    )
    casts = (a_cast(two_charges, 290_000),)
    assert defensives_up_at(casts, (two_charges,), 11, DEATH_MS, visible_from_ms=LOG_FROM) == ()


def test_only_this_players_casts_count() -> None:
    # Ours proves ownership early; theirs would have blocked the window had the
    # rule read the whole roster's casts.
    casts = owns_both() + (a_cast(ICE_BLOCK, 290_000, actor_id=12),)
    assert "Ice Block" in defensives_up_at(casts, ABILITIES, 11, DEATH_MS, visible_from_ms=LOG_FROM)


def test_the_order_follows_the_ability_list() -> None:
    assert defensives_up_at(
        owns_both(), (BARRIER, ICE_BLOCK), 11, DEATH_MS,
        visible_from_ms=LOG_FROM,
    ) == (
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


def locate_in_a_run(death: Death) -> str:
    """The real `locate` a caller would build for `a_run()`'s single pull."""
    return pull_offset(a_run().pulls, death)


def test_a_death_with_a_defensive_available_is_a_finding() -> None:
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, owns_both(), DEFENSIVES, (a_death(),), locate=locate_in_a_run,
        visible_from_ms=LOG_FROM, shape="run",
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
        run.players, casts, DEFENSIVES, (a_death(),), locate=locate_in_a_run,
        visible_from_ms=LOG_FROM, shape="run",
    ) == []


def test_a_player_who_cast_none_of_their_defensives_says_nothing_here() -> None:
    # The never-cast case belongs to the other analyser, which discloses that a
    # missing talent explains it just as well as a missing button press.
    run = a_run()
    assert analyse_defensives_at_death(
        run.players, (), DEFENSIVES, (a_death(),), locate=locate_in_a_run, visible_from_ms=LOG_FROM,
        shape="run",
    ) == []


def test_a_spec_the_data_file_does_not_cover_says_nothing() -> None:
    empty = Defensives(entries=())
    run = a_run()
    assert analyse_defensives_at_death(
        run.players, owns_both(), empty, (a_death(),), locate=locate_in_a_run,
        visible_from_ms=LOG_FROM, shape="run",
    ) == []


def test_a_player_who_did_not_die_says_nothing() -> None:
    run = a_run()
    assert analyse_defensives_at_death(
        run.players, owns_both(), DEFENSIVES, (), locate=locate_in_a_run, visible_from_ms=LOG_FROM,
        shape="run",
    ) == []


def test_the_title_counts_only_the_deaths_that_qualified() -> None:
    # The first death has Ice Block up. By the second, Ice Block has been cast
    # and Barrier is inside its own window, so nothing was available.
    casts = owns_both() + (a_cast(BARRIER, 280_000), a_cast(ICE_BLOCK, 305_000))
    deaths = (a_death(at_ms=300_000), a_death(at_ms=310_000))
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, casts, DEFENSIVES, deaths, locate=locate_in_a_run, visible_from_ms=LOG_FROM,
        shape="run",
    )
    assert "once" in findings[0].title


def test_the_pull_index_comes_from_the_first_qualifying_death() -> None:
    # Nothing is up at the earlier death; Barrier has come back round by the later one.
    casts = owns_both() + (a_cast(BARRIER, 280_000), a_cast(ICE_BLOCK, 305_000))
    early = a_death(at_ms=310_000).model_copy(update={"pull_index": 7})
    late = a_death(at_ms=380_000).model_copy(update={"pull_index": 9})
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, casts, DEFENSIVES, (early, late), locate=locate_in_a_run,
        visible_from_ms=LOG_FROM, shape="run",
    )
    assert findings[0].pull_index == 9


def test_the_evidence_names_the_killing_blow_and_what_was_up() -> None:
    run = a_run()
    findings = analyse_defensives_at_death(
        run.players, owns_both(), DEFENSIVES, (a_death(),), locate=locate_in_a_run,
        visible_from_ms=LOG_FROM, shape="run",
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
            run.players, casts, DEFENSIVES, deaths, locate=locate_in_a_run,
            visible_from_ms=LOG_FROM, shape="run",
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
            run.players, casts, DEFENSIVES, deaths, locate=locate_in_a_run,
            visible_from_ms=LOG_FROM, shape="run",
        )
    }

    assert ids == {"defensives.unused.briala.11", "defensives.unused.briala.12"}


# --- progression.repeat.ready: the rule above, pooled across a boss's pulls ---
#
# Each pull is judged on its own casts, and the pulls are added up. Every pull
# below runs 600 seconds from `an_attempt`'s `fight_id * 1_000_000`, so pull
# windows never overlap.

IBF = DefensiveAbility(ability_id=48792, name="Icebound Fortitude", cooldown_seconds=180.0)
AMS = DefensiveAbility(ability_id=48707, name="Anti-Magic Shell", cooldown_seconds=60.0)
BLOOD = Defensives(entries=(("DeathKnight/Blood", (IBF, AMS)),))
"""Icebound Fortitude listed first: an insertion-ordered sort puts it first,
and a name-ordered one puts Anti-Magic Shell first."""

EMBERKIN = Player(actor_id=1, name="Emberkin", class_name="DeathKnight", spec="Blood",
                  item_level=600)
STONEWAKE = Player(actor_id=2, name="Stonewake", class_name="Mage", spec="Arcane",
                   item_level=600)


def a_pull(
    fight_id: int,
    *,
    deaths: tuple[tuple[Player, float], ...] = (),
    casts: tuple[tuple[Player, DefensiveAbility, float], ...] = (),
    players: tuple[Player, ...] = (EMBERKIN,),
    start_ms: int | None = None,
) -> LoadedEncounter:
    """One pull, its deaths and casts given as seconds after the pull's start.

    `start_ms` overrides the pull's own start, which `an_attempt` otherwise
    derives from `fight_id * 1_000_000` -- far enough apart that two pulls
    built that way never sit close together. Passing it is how a test places
    one pull shortly after another, the way a real raid's pulls do.
    """
    overrides: dict[str, object] = {"players": players}
    if start_ms is not None:
        overrides["start_ms"] = start_ms
        overrides["end_ms"] = start_ms + 600_000
    encounter = an_attempt(fight_id, 50.0, 600.0, **overrides)
    start = encounter.start_ms
    return LoadedEncounter(
        encounter=encounter,
        deaths=tuple(
            Death(player_name=who.name, actor_id=who.actor_id,
                  timestamp_ms=start + int(at * 1000), killing_blow="Void Bolt")
            for who, at in deaths
        ),
        casts=tuple(
            CastEvent(actor_id=who.actor_id, ability_id=ability.ability_id,
                      ability_name=ability.name, timestamp_ms=start + int(at * 1000))
            for who, ability, at in casts
        ),
    )


def owned_and_died(fight_id: int, *abilities: DefensiveAbility) -> LoadedEncounter:
    """Emberkin casts each ability at 1s -- proof of owning it -- and dies at 400s.

    400s is past every window here (Icebound Fortitude's is 180 + 10), so each
    ability cast is up at the death.
    """
    return a_pull(
        fight_id,
        deaths=((EMBERKIN, 400.0),),
        casts=tuple((EMBERKIN, ability, 1.0) for ability in abilities),
    )


def test_an_ability_up_at_deaths_on_two_pulls_names_the_player() -> None:
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF)), BLOOD
    )
    assert [f.id for f in findings] == ["progression.repeat.ready.emberkin"]
    (finding,) = findings
    assert finding.title == "Emberkin: Icebound Fortitude up at 2 of 2 deaths"
    assert finding.ability_id == IBF.ability_id
    assert finding.ability_name == "Icebound Fortitude"
    assert finding.evidence == (
        "DeathKnight Blood", "Icebound Fortitude up at 2 of 2 deaths",
    )
    assert finding.confidence is Confidence.INFERRED
    assert finding.player_slug == ""


def test_two_deaths_inside_one_pull_are_that_pulls_claim_not_this_one() -> None:
    """A battle resurrection, then a second death: both up, both on pull 1."""
    twice = a_pull(
        1,
        deaths=((EMBERKIN, 300.0), (EMBERKIN, 500.0)),
        casts=((EMBERKIN, IBF, 1.0),),
    )
    quiet = a_pull(2, casts=((EMBERKIN, IBF, 1.0),))
    assert repeat_defensives_up(a_loaded_series(twice, quiet), BLOOD) == []


def test_a_death_on_a_pull_without_the_ability_cast_is_left_out_of_its_denominator() -> None:
    """Pull 3 holds a death and no Icebound Fortitude cast: unknown, not "not up"."""
    unowned = a_pull(3, deaths=((EMBERKIN, 400.0),))
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF), unowned), BLOOD
    )
    assert findings[0].title == "Emberkin: Icebound Fortitude up at 2 of 2 deaths"


def test_a_pressed_ability_stays_in_the_denominator_and_out_of_the_count() -> None:
    """Pull 3: owned, pressed at 380s inside its window, so judged and not up."""
    pressed = a_pull(
        3,
        deaths=((EMBERKIN, 400.0),),
        casts=((EMBERKIN, IBF, 1.0), (EMBERKIN, IBF, 380.0)),
    )
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF), pressed), BLOOD
    )
    assert findings[0].title == "Emberkin: Icebound Fortitude up at 2 of 3 deaths"


def test_a_talent_cast_on_one_pull_is_not_owned_on_the_next() -> None:
    """The pull-by-pull ruling: pull 2 never casts it, so pull 2's death says nothing.

    Judged across the whole night instead -- both the casts handed to
    `defensives_up_at` and the `cast_ids` ownership gate drawing from every
    pull rather than just their own -- pull 1's cast would make it "up" on
    pull 2 as well, and the player would be named at 2 of 2. The design's
    rejected alternative; going night-wide on only one of the two lines does
    not reproduce it.
    """
    swapped_out = a_pull(2, deaths=((EMBERKIN, 400.0),))
    assert repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), swapped_out), BLOOD
    ) == []


def test_several_abilities_are_named_in_one_finding_tied_counts_by_name() -> None:
    findings = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF, AMS), owned_and_died(2, IBF, AMS)), BLOOD
    )
    (finding,) = findings
    assert finding.title == "Emberkin: 2 defensives up at more than one death"
    assert finding.ability_id is None
    assert finding.evidence == (
        "DeathKnight Blood",
        "Anti-Magic Shell up at 2 of 2 deaths",
        "Icebound Fortitude up at 2 of 2 deaths",
    )


def test_abilities_are_ordered_by_count_before_name() -> None:
    """Icebound Fortitude up 3 times, Anti-Magic Shell 2: count wins over the alphabet.

    Listed Anti-Magic Shell first, so neither insertion order nor name order
    can produce the expected order by accident.
    """
    ams_first = Defensives(entries=(("DeathKnight/Blood", (AMS, IBF)),))
    pressed_ams = a_pull(
        3,
        deaths=((EMBERKIN, 400.0),),
        casts=((EMBERKIN, IBF, 1.0), (EMBERKIN, AMS, 1.0), (EMBERKIN, AMS, 380.0)),
    )
    (finding,) = repeat_defensives_up(
        a_loaded_series(
            owned_and_died(1, IBF, AMS), owned_and_died(2, IBF, AMS), pressed_ams
        ),
        ams_first,
    )
    assert finding.evidence[1:] == (
        "Icebound Fortitude up at 3 of 3 deaths",
        "Anti-Magic Shell up at 2 of 3 deaths",
    )


def test_a_player_absent_from_a_pull_is_judged_on_the_pulls_they_played() -> None:
    """Emberkin sits out pull 1: a roster read from the first pull alone would miss him."""
    benched = a_pull(1, players=(STONEWAKE,), deaths=((STONEWAKE, 400.0),))
    findings = repeat_defensives_up(
        a_loaded_series(benched, owned_and_died(2, IBF), owned_and_died(3, IBF)), BLOOD
    )
    assert [f.title for f in findings] == ["Emberkin: Icebound Fortitude up at 2 of 2 deaths"]


def test_two_players_sharing_a_slug_get_two_ids() -> None:
    accented = Player(actor_id=1, name="Bríala", class_name="DeathKnight", spec="Blood",
                      item_level=600)
    plain = Player(actor_id=3, name="Briala", class_name="DeathKnight", spec="Blood",
                   item_level=600)

    def both_die(fight_id: int) -> LoadedEncounter:
        return a_pull(
            fight_id,
            players=(accented, plain),
            deaths=((accented, 400.0), (plain, 410.0)),
            casts=((accented, IBF, 1.0), (plain, IBF, 1.0)),
        )

    findings = repeat_defensives_up(a_loaded_series(both_die(1), both_die(2)), BLOOD)
    assert sorted(f.id for f in findings) == [
        "progression.repeat.ready.briala.1",
        "progression.repeat.ready.briala.3",
    ]


def test_a_spec_absent_from_the_data_file_names_nobody() -> None:
    def mage_dies(fight_id: int) -> LoadedEncounter:
        return a_pull(
            fight_id, players=(STONEWAKE,), deaths=((STONEWAKE, 400.0),),
            casts=((STONEWAKE, IBF, 1.0),),
        )

    assert repeat_defensives_up(a_loaded_series(mage_dies(1), mage_dies(2)), BLOOD) == []


def test_the_detail_says_it_is_a_question_and_how_it_was_judged() -> None:
    (finding,) = repeat_defensives_up(
        a_loaded_series(owned_and_died(1, IBF), owned_and_died(2, IBF)), BLOOD
    )
    assert "pull by pull" in finding.detail
    assert "a question to ask, not a mistake to fix" in finding.detail


def test_a_death_whose_window_reaches_into_the_pull_before_is_left_out_of_both_counts() -> None:
    """Real pulls can restart less than a cooldown after the last one ended, and cooldowns carry.

    Anti-Magic Shell's window is (60 + 10) seconds. Pull 1 presses it at 590s
    of a 600s pull, after a death at 100s where it reads up. Pull 2 starts 30s
    after pull 1 ends -- only 40s past that late press -- and the player dies
    there 20s in, battle-rezzed, then presses it again at 200s to prove they
    still own it. That death's window reaches 50s back past pull 2's first
    second, where pull 1's press really did spend the shell: a cooldown carries
    over between pulls. It is not judged, so it counts neither as up nor as a
    death judged. Pull 3 dies judged at 100s, so the player is named -- up at
    two of two deaths, not two of three, and not three of three.
    """
    pull_one = a_pull(
        1,
        deaths=((EMBERKIN, 100.0),),
        casts=((EMBERKIN, AMS, 590.0),),
    )
    pull_two = a_pull(
        2,
        start_ms=pull_one.encounter.end_ms + 30_000,
        deaths=((EMBERKIN, 20.0),),
        casts=((EMBERKIN, AMS, 200.0),),
    )
    pull_three = a_pull(
        3,
        deaths=((EMBERKIN, 100.0),),
        casts=((EMBERKIN, AMS, 200.0),),
    )
    findings = repeat_defensives_up(a_loaded_series(pull_one, pull_two, pull_three), BLOOD)
    assert [f.title for f in findings] == ["Emberkin: Anti-Magic Shell up at 2 of 2 deaths"]


def test_pooled_counts_equal_the_pull_rows_defensives_up_at_would_give() -> None:
    """The design's core promise: pooled is exactly the sum of the pull rows beneath it.

    `analyse_defensives_at_death` folds a player's per-death lines into one
    finding's free-text evidence rather than a per-ability count, so there is
    no clean field of its to compare against. This instead calls
    `defensives_up_at` once per pull per player per ability -- the same call
    `repeat_defensives_up` itself makes -- and sums the result by hand, over a
    series with two players, two abilities and three pulls, then checks that
    `repeat_defensives_up`'s own findings say exactly the same numbers.
    """
    kirillitsa = Player(
        actor_id=3, name="Кириллица", class_name="DeathKnight", spec="Blood", item_level=600
    )
    roster = (EMBERKIN, kirillitsa)
    pull_one = a_pull(
        1, players=roster,
        deaths=((EMBERKIN, 400.0), (kirillitsa, 400.0)),
        casts=((EMBERKIN, IBF, 1.0), (kirillitsa, AMS, 1.0)),
    )
    pull_two = a_pull(
        2, players=roster,
        deaths=((EMBERKIN, 400.0), (kirillitsa, 400.0)),
        casts=((EMBERKIN, IBF, 1.0), (kirillitsa, AMS, 1.0)),
    )
    # A third press inside its own window: Kirillitsa's Anti-Magic Shell stays
    # judged on this pull but does not count as up, so her denominator grows
    # without her count doing the same.
    pull_three = a_pull(
        3, players=roster,
        deaths=((kirillitsa, 400.0),),
        casts=((kirillitsa, AMS, 1.0), (kirillitsa, AMS, 380.0)),
    )
    pulls = (pull_one, pull_two, pull_three)
    series = a_loaded_series(*pulls)

    tallies: dict[tuple[int, int], list[int]] = {}
    for pull in pulls:
        for player in pull.players:
            abilities = BLOOD.for_spec(player.class_name, player.spec)
            cast_ids = {c.ability_id for c in pull.casts if c.actor_id == player.actor_id}
            for death in pull.deaths:
                if death.actor_id != player.actor_id:
                    continue
                up_now = defensives_up_at(
                    pull.casts, abilities, player.actor_id, death.timestamp_ms,
                    visible_from_ms=pull.window_ms[0],
                )
                for ability in abilities:
                    if ability.ability_id not in cast_ids:
                        continue
                    key = (player.actor_id, ability.ability_id)
                    tally = tallies.setdefault(key, [0, 0])
                    tally[1] += 1
                    if ability.name in up_now:
                        tally[0] += 1

    findings = {finding.id: finding for finding in repeat_defensives_up(series, BLOOD)}
    emberkin_up, emberkin_judged = tallies[(EMBERKIN.actor_id, IBF.ability_id)]
    kirillitsa_up, kirillitsa_judged = tallies[(kirillitsa.actor_id, AMS.ability_id)]
    assert findings["progression.repeat.ready.emberkin"].evidence[1:] == (
        f"Icebound Fortitude up at {emberkin_up} of {emberkin_judged} deaths",
    )
    assert findings["progression.repeat.ready.player"].evidence[1:] == (
        f"Anti-Magic Shell up at {kirillitsa_up} of {kirillitsa_judged} deaths",
    )


# --- a window reaching before the log ----------------------------------------

ORIGIN = 4_000_000
"""The log's first second in the cases below, far from zero as report timestamps are."""


def test_a_window_starting_at_the_logs_first_second_is_judged() -> None:
    # Prismatic Barrier's window is (25 + 10) seconds; cast after the death to prove it is owned.
    owns = (a_cast(BARRIER, ORIGIN + 100_000),)
    assert defensives_up_at(
        owns, (BARRIER,), 11, ORIGIN + 35_000, visible_from_ms=ORIGIN
    ) == ("Prismatic Barrier",)


def test_a_window_reaching_one_millisecond_before_the_log_is_not_judged() -> None:
    owns = (a_cast(BARRIER, ORIGIN + 100_000),)
    assert defensives_up_at(
        owns, (BARRIER,), 11, ORIGIN + 35_000 - 1, visible_from_ms=ORIGIN
    ) == ()


def test_the_finding_says_what_it_does_not_judge_in_its_own_setting() -> None:
    for shape in ("run", "fight"):
        [finding] = analyse_defensives_at_death(
            a_run().players, owns_both(), DEFENSIVES, (a_death(),), locate=locate_in_a_run,
            visible_from_ms=LOG_FROM, shape=shape,
        )
        assert (
            "An ability whose base cooldown reaches back before the "
            f"{shape}'s first second is not judged, since a press before it is invisible."
        ) in finding.detail

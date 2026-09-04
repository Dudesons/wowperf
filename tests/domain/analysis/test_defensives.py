# ABOUTME: Behaviour tests for the one defensive claim the log can support.
# ABOUTME: Never cast at all is a fact; not cast at the right time is not, and is not claimed.

from wowperf.domain.analysis.defensives import analyse_defensives
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
            Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
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


def test_a_defensive_never_cast_is_reported_as_inferred() -> None:
    # Prismatic Barrier's 25s cooldown fits four times into this 100s pull, so a
    # single press of it now also qualifies for a ceiling finding (§5.7); scope
    # this assertion to the never-cast claim it was written to check.
    findings = analyse_defensives(a_run(), (cast(11, 235450),), DEFENSIVES, ())
    never_cast = [f for f in findings if not f.id.startswith("defensives.ceiling.")]
    assert len(never_cast) == 1
    assert "Ice Block" in never_cast[0].title
    assert never_cast[0].confidence is Confidence.INFERRED
    assert never_cast[0].seconds_lost is None


def test_a_defensive_cast_once_is_not_reported() -> None:
    findings = analyse_defensives(
        a_run(), (cast(11, 235450), cast(11, 45438)), DEFENSIVES, ()
    )
    never_cast = [f for f in findings if not f.id.startswith("defensives.ceiling.")]
    assert never_cast == []


def test_the_finding_admits_the_ability_may_have_been_unavailable() -> None:
    findings = analyse_defensives(a_run(), (), DEFENSIVES, ())
    assert any("cooldown" in f.detail.lower() for f in findings)


def test_a_spec_absent_from_the_list_produces_nothing() -> None:
    # Sublime is an Elemental Shaman and the fixture only knows Arcane Mages.
    findings = analyse_defensives(a_run(), (), DEFENSIVES, ())
    assert all("Sublime" not in finding.title for finding in findings)


def test_another_players_cast_does_not_excuse_this_player() -> None:
    findings = analyse_defensives(a_run(), (cast(12, 45438),), DEFENSIVES, ())
    assert any("Ice Block" in finding.title for finding in findings)


def test_a_cast_outside_every_pull_still_counts_as_used() -> None:
    # pull_index=None means the cast landed outside any pull window (e.g. between
    # packs). The player still pressed the button, so it is not "never cast".
    outside_pull = CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                              timestamp_ms=1_000, pull_index=None)
    findings = analyse_defensives(a_run(), (cast(11, 235450), outside_pull), DEFENSIVES, ())
    never_cast = [f for f in findings if not f.id.startswith("defensives.ceiling.")]
    assert never_cast == []


def test_two_players_of_the_same_spec_are_reported_independently() -> None:
    run = a_run()
    other_mage = Player(actor_id=13, name="Othermage", class_name="Mage", spec="Arcane",
                         item_level=300)
    run = run.model_copy(update={"players": run.players + (other_mage,)})
    findings = analyse_defensives(run, (cast(11, 235450), cast(11, 45438)), DEFENSIVES, ())
    never_cast = [f for f in findings if not f.id.startswith("defensives.ceiling.")]
    assert len(never_cast) == 2
    assert all("Othermage" in finding.title for finding in never_cast)


def test_same_named_players_get_distinct_finding_ids() -> None:
    run = a_run()
    twin = Player(actor_id=99, name="Uglymage", class_name="Mage", spec="Arcane",
                  item_level=300)
    run = run.model_copy(update={"players": run.players + (twin,)})
    findings = analyse_defensives(run, (), DEFENSIVES, ())
    ids = [finding.id for finding in findings]
    assert len(ids) == len(set(ids))


def test_defensives_with_no_entries_produces_nothing() -> None:
    findings = analyse_defensives(a_run(), (), Defensives(entries=()), ())
    assert findings == []


def a_death(actor_id: int, seconds: float | None) -> Death:
    return Death(
        player_name="Tank",
        actor_id=actor_id,
        timestamp_ms=0,
        killing_blow="Something",
        seconds_until_next_action=seconds,
    )


def test_a_defensive_pressed_far_below_its_ceiling_is_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "1 of" in ceiling[0].title
    assert ceiling[0].confidence is Confidence.INFERRED
    assert ceiling[0].seconds_lost is None


def test_a_defensive_never_pressed_produces_no_ceiling_finding() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)

    findings = analyse_defensives(run, (), BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []
    assert findings_by_prefix(findings, "defensives.Tank.") != []


def test_a_defensive_pressed_close_to_its_ceiling_is_not_reported() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    # 1800s / 180s = a ceiling of 10; eight presses is not a story.
    casts = tuple(a_cast(actor_id=1, ability_id=48792) for _ in range(8))

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_a_run_too_short_for_a_meaningful_ceiling_reports_nothing() -> None:
    # 300s / 180s = a ceiling of 1.67, below MIN_CEILING_USES.
    run = a_run_with_one_blood_death_knight(pull_seconds=300.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, ())

    assert findings_by_prefix(findings, "defensives.ceiling.") == []


def test_time_spent_dead_does_not_count_towards_the_ceiling() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)
    # 1200s of the 1800s were spent dead, so the ceiling falls from 10 to 3.33.
    findings = analyse_defensives(run, casts, BLOOD_DEFENSIVES, (a_death(1, 1200.0),))
    ceiling = findings_by_prefix(findings, "defensives.ceiling.")

    assert len(ceiling) == 1
    assert "3 times" in ceiling[0].title, ceiling[0].title


def test_the_ceiling_detail_says_defensives_are_situational() -> None:
    run = a_run_with_one_blood_death_knight(pull_seconds=1800.0)
    casts = (a_cast(actor_id=1, ability_id=48792),)

    finding = findings_by_prefix(
        analyse_defensives(run, casts, BLOOD_DEFENSIVES, ()), "defensives.ceiling."
    )[0]

    assert "incoming damage" in finding.detail

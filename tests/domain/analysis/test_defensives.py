# ABOUTME: Behaviour tests for the one defensive claim the log can support.
# ABOUTME: Never cast at all is a fact; not cast at the right time is not, and is not claimed.

from wowperf.domain.analysis.defensives import analyse_defensives
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run
from wowperf.domain.season import DefensiveAbility, Defensives

DEFENSIVES = Defensives(
    entries=(
        (
            "Mage/Arcane",
            (
                DefensiveAbility(ability_id=235450, name="Prismatic Barrier"),
                DefensiveAbility(ability_id=45438, name="Ice Block"),
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
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
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


def test_a_defensive_never_cast_is_reported_as_inferred() -> None:
    findings = analyse_defensives(a_run(), (cast(11, 235450),), DEFENSIVES)
    assert len(findings) == 1
    assert "Ice Block" in findings[0].title
    assert findings[0].confidence is Confidence.INFERRED
    assert findings[0].seconds_lost is None


def test_a_defensive_cast_once_is_not_reported() -> None:
    findings = analyse_defensives(
        a_run(), (cast(11, 235450), cast(11, 45438)), DEFENSIVES
    )
    assert findings == []


def test_the_finding_admits_the_ability_may_have_been_unavailable() -> None:
    findings = analyse_defensives(a_run(), (), DEFENSIVES)
    assert any("cooldown" in f.detail.lower() for f in findings)


def test_a_spec_absent_from_the_list_produces_nothing() -> None:
    # Sublime is an Elemental Shaman and the fixture only knows Arcane Mages.
    findings = analyse_defensives(a_run(), (), DEFENSIVES)
    assert all("Sublime" not in finding.title for finding in findings)


def test_another_players_cast_does_not_excuse_this_player() -> None:
    findings = analyse_defensives(a_run(), (cast(12, 45438),), DEFENSIVES)
    assert any("Ice Block" in finding.title for finding in findings)


def test_a_cast_outside_every_pull_still_counts_as_used() -> None:
    # pull_index=None means the cast landed outside any pull window (e.g. between
    # packs). The player still pressed the button, so it is not "never cast".
    outside_pull = CastEvent(actor_id=11, ability_id=45438, ability_name="Ice Block",
                              timestamp_ms=1_000, pull_index=None)
    findings = analyse_defensives(a_run(), (cast(11, 235450), outside_pull), DEFENSIVES)
    assert findings == []


def test_two_players_of_the_same_spec_are_reported_independently() -> None:
    run = a_run()
    other_mage = Player(actor_id=13, name="Othermage", class_name="Mage", spec="Arcane",
                         item_level=300)
    run = run.model_copy(update={"players": run.players + (other_mage,)})
    findings = analyse_defensives(run, (cast(11, 235450), cast(11, 45438)), DEFENSIVES)
    assert len(findings) == 2
    assert all("Othermage" in finding.title for finding in findings)


def test_same_named_players_get_distinct_finding_ids() -> None:
    run = a_run()
    twin = Player(actor_id=99, name="Uglymage", class_name="Mage", spec="Arcane",
                  item_level=300)
    run = run.model_copy(update={"players": run.players + (twin,)})
    findings = analyse_defensives(run, (), DEFENSIVES)
    ids = [finding.id for finding in findings]
    assert len(ids) == len(set(ids))


def test_defensives_with_no_entries_produces_nothing() -> None:
    findings = analyse_defensives(a_run(), (), Defensives(entries=()))
    assert findings == []

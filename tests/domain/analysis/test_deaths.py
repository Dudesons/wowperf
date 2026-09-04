# ABOUTME: Behaviour tests for what deaths actually cost and which ones caused others.
# ABOUTME: A death with no measured cost must stay uncounted rather than get a default.

from wowperf.domain.analysis.deaths import analyse_deaths
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence
from wowperf.domain.model import EnemyNpc, Player, Pull, Run


def a_run() -> Run:
    pulls = (
        Pull(index=0, pull_id=1, name="Trash", encounter_id=0, start_ms=0, end_ms=60_000,
             killed=True, x=10, y=20, enemies=(EnemyNpc(actor_id=1, game_id=100),)),
    )
    return Run(
        report_code="abc123", fight_id=36, dungeon_name="Den of Nalorakk",
        keystone_level=16, affix_ids=(), keystone_time_ms=300_000, keystone_bonus=1,
        count_reached=744, count_required=729, npc_counts=(),
        players=(
            Player(actor_id=11, name="Uglymage", class_name="Mage", spec="Arcane",
                   item_level=318),
            Player(actor_id=12, name="Sublime", class_name="Shaman", spec="Elemental",
                   item_level=311),
        ),
        pulls=pulls,
    )


def a_death(name: str, actor_id: int, at: int, cost: float | None) -> Death:
    return Death(player_name=name, actor_id=actor_id, timestamp_ms=at,
                 killing_blow="Molten Scar", pull_index=0,
                 seconds_until_next_action=cost)


def test_the_total_cost_is_the_measured_time_not_played() -> None:
    findings = analyse_deaths(
        a_run(),
        (a_death("Uglymage", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, 12.5)),
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 32.5
    assert total.confidence is Confidence.MEASURED


def test_a_death_with_no_measured_cost_is_excluded_and_said_so() -> None:
    findings = analyse_deaths(
        a_run(), (a_death("Uglymage", 11, 1_000, 20.0), a_death("Sublime", 12, 40_000, None))
    )
    total = next(f for f in findings if f.id == "deaths.total")
    assert total.seconds_lost == 20.0
    assert any("1 death" in item and "not measured" in item for item in total.evidence)


def test_no_deaths_produces_no_findings() -> None:
    assert analyse_deaths(a_run(), ()) == []


def test_deaths_close_together_are_reported_as_one_chain() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 30_000, 10.0),
            a_death("Sublime", 12, 33_000, 8.0),
        ),
    )
    chain = next(f for f in findings if f.id.startswith("deaths.chain."))
    assert chain.seconds_lost == 18.0
    assert "Uglymage" in chain.detail
    assert chain.confidence is Confidence.MEASURED


def test_deaths_far_apart_are_reported_separately() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 1_000, 10.0),
            a_death("Sublime", 12, 200_000, 8.0),
        ),
    )
    assert [f.id for f in findings if f.id.startswith("deaths.chain.")] == []
    assert len([f for f in findings if f.id.startswith("deaths.single.")]) == 2


def test_a_repeat_dier_is_named() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 1_000, 10.0),
            a_death("Uglymage", 11, 200_000, 8.0),
        ),
    )
    repeat = next(f for f in findings if f.id == "deaths.repeat.Uglymage")
    assert repeat.seconds_lost == 18.0
    assert "2" in repeat.detail


def test_a_single_death_is_reported_alone_with_correct_grammar() -> None:
    findings = analyse_deaths(a_run(), (a_death("Uglymage", 11, 1_000, 10.0),))
    assert [f.id for f in findings if f.id.startswith("deaths.chain.")] == []
    assert [f.id for f in findings if f.id.startswith("deaths.repeat.")] == []
    singles = [f for f in findings if f.id.startswith("deaths.single.")]
    assert [f.id for f in singles] == ["deaths.single.0"]

    total = next(f for f in findings if f.id == "deaths.total")
    assert total.title.startswith("1 death cost"), total.title


def test_a_wholly_unmeasured_death_reports_no_seconds_lost_rather_than_zero() -> None:
    findings = analyse_deaths(a_run(), (a_death("Uglymage", 11, 1_000, None),))
    single = next(f for f in findings if f.id == "deaths.single.0")
    assert single.seconds_lost is None
    assert "cannot be measured" in single.detail


def test_a_chain_of_wholly_unmeasured_deaths_reports_no_seconds_lost() -> None:
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 30_000, None),
            a_death("Sublime", 12, 33_000, None),
        ),
    )
    chain = next(f for f in findings if f.id.startswith("deaths.chain."))
    assert chain.seconds_lost is None
    assert "cannot be measured" in chain.detail


def test_a_transitive_chain_groups_all_three_deaths() -> None:
    # A-B within CHAIN_WINDOW_MS, B-C within CHAIN_WINDOW_MS, A-C outside it: the
    # module groups each death against the last one already in its group, so all
    # three belong to a single chain rather than A splitting off from C.
    findings = analyse_deaths(
        a_run(),
        (
            a_death("Uglymage", 11, 0, 10.0),
            a_death("Sublime", 12, 9_000, 8.0),
            a_death("Uglymage", 11, 17_000, 5.0),
        ),
    )
    chains = [f for f in findings if f.id.startswith("deaths.chain.")]
    assert len(chains) == 1
    assert chains[0].title == "3 deaths within 10s"
    assert chains[0].seconds_lost == 23.0

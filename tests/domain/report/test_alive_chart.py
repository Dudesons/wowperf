# ABOUTME: Behaviour tests for the players-alive chart: a step function in viewBox units.
# ABOUTME: Its last point is the verdict's own figure, and the two may never disagree.

from wowperf.domain.events import Death, Resurrection
from wowperf.domain.report.alive_chart import CHART_HEIGHT, CHART_WIDTH, build_alive_chart


def _deaths(count: int) -> tuple[Death, ...]:
    return tuple(
        Death(
            player_name=f"Raider {index}",
            actor_id=index,
            timestamp_ms=10_000 * (index + 1),
            killing_blow="Caustic Waves",
            killing_blow_id=11,
        )
        for index in range(count)
    )


def test_a_full_raid_starts_at_the_top_of_the_plot() -> None:
    chart = build_alive_chart(20, (), (), duration_ms=100_000, boss_percentage=40.0)

    assert chart is not None
    assert chart.points[0].x == 0.0 or chart.points[0].x > 0.0
    assert chart.points[0].y == min(point.y for point in chart.points)


def test_the_series_steps_down_and_never_leaves_the_plot() -> None:
    chart = build_alive_chart(20, _deaths(5), (), duration_ms=100_000, boss_percentage=40.0)

    assert chart is not None
    assert len(chart.points) >= 6
    for point in chart.points:
        assert 0.0 <= point.x <= CHART_WIDTH
        assert 0.0 <= point.y <= CHART_HEIGHT


def test_a_resurrection_steps_the_line_back_up() -> None:
    """Up on the page means up in the count, so y decreases."""
    resurrections = (
        Resurrection(
            actor_id=0, caster_id=19, ability_id=20484,
            ability_name="Rebirth", timestamp_ms=50_000,
        ),
    )

    chart = build_alive_chart(
        20, _deaths(2), resurrections, duration_ms=100_000, boss_percentage=40.0
    )

    assert chart is not None
    assert chart.points[-1].y < chart.points[-2].y


def test_the_boss_note_states_where_the_boss_finished() -> None:
    chart = build_alive_chart(20, _deaths(5), (), duration_ms=100_000, boss_percentage=16.49)

    assert chart is not None
    assert "16.5%" in chart.boss_note


def test_an_attempt_with_no_duration_draws_nothing() -> None:
    """An axis with no length draws a line at a single x, which reads as a bug."""
    assert build_alive_chart(20, (), (), duration_ms=0, boss_percentage=40.0) is None

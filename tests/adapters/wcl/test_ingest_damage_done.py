# ABOUTME: The damage done graph, from one API response to domain series.
# ABOUTME: The rate-to-amount conversion is the one line here worth most of the tests.

from typing import Any

from wowperf.adapters.wcl.ingest import build_damage_done


def a_payload(*series: dict[str, Any]) -> dict[str, Any]:
    return {
        "reportData": {
            "report": {
                "graph": {
                    "data": {
                        "series": list(series),
                        "startTime": 0,
                        "endTime": 60_000,
                    }
                }
            }
        }
    }


def a_series(actor_id: Any, points: list[float], interval: float = 6000.0) -> dict[str, Any]:
    return {
        "id": actor_id,
        "guid": 123,
        "type": "Warrior",
        "pointStart": 1000,
        "pointInterval": interval,
        "total": 999,
        "data": points,
    }


def test_a_points_rate_becomes_the_damage_that_bucket_held() -> None:
    """The response states damage per second; the domain holds damage.

    100 a second over a six-second bucket is 600, and the two figures are
    far enough apart that dropping the conversion cannot pass for rounding.
    """
    series = build_damage_done(a_payload(a_series(7, [100.0], interval=6000.0)))
    assert series[0].amounts == (600,)


def test_every_bucket_is_converted_not_only_the_first() -> None:
    series = build_damage_done(a_payload(a_series(7, [100.0, 50.0, 0.0], interval=6000.0)))
    assert series[0].amounts == (600, 300, 0)


def test_the_interval_the_response_states_is_the_one_used() -> None:
    """A fixed six seconds would pass the tests above and be wrong here."""
    series = build_damage_done(a_payload(a_series(7, [100.0], interval=2500.0)))
    assert series[0].amounts == (250,)


def test_the_total_series_is_dropped() -> None:
    """Its id is the string "Total" where a player's is an int. It is the sum
    of the others, and a run-wide damage total in the model is one import away
    from a page that ranks -- which the postmortem design section 5.5 refuses."""
    payload = a_payload(a_series(7, [100.0]), a_series("Total", [4242.0]))
    series = build_damage_done(payload)
    assert [one.actor_id for one in series] == [7]
    assert all(4242 * 6 not in one.amounts for one in series)


def test_each_series_keeps_its_own_actor_and_start() -> None:
    payload = a_payload(a_series(7, [100.0]), a_series(9, [50.0]))
    series = build_damage_done(payload)
    assert [(one.actor_id, one.point_start_ms) for one in series] == [(7, 1000), (9, 1000)]
    assert [one.interval_ms for one in series] == [6000.0, 6000.0]


def test_a_series_with_no_interval_is_skipped_rather_than_divided_by() -> None:
    assert build_damage_done(a_payload(a_series(7, [100.0], interval=0.0))) == ()


def test_a_response_carrying_no_graph_ingests_to_nothing() -> None:
    assert build_damage_done({"reportData": {"report": {"graph": None}}}) == ()

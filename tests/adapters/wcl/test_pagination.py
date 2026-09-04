# ABOUTME: Behaviour tests for the events cursor loop.
# ABOUTME: A dropped page silently truncates a run, so paging must be covered directly.

from typing import Any

from wowperf.adapters.wcl.pagination import fetch_all_events


def test_pages_are_followed_until_the_cursor_is_null() -> None:
    pages: list[dict[str, Any]] = [
        {"reportData": {"report": {"events": {"data": [{"t": 1}], "nextPageTimestamp": 500}}}},
        {"reportData": {"report": {"events": {"data": [{"t": 2}], "nextPageTimestamp": None}}}},
    ]
    seen_start_times: list[Any] = []

    def execute(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        seen_start_times.append(variables["startTime"])
        return pages[len(seen_start_times) - 1]

    events = fetch_all_events(execute, "query", {"startTime": 0})

    assert events == [{"t": 1}, {"t": 2}]
    assert seen_start_times == [0, 500]


def test_a_single_page_makes_one_call() -> None:
    calls: list[int] = []

    def execute(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}

    assert fetch_all_events(execute, "query", {"startTime": 0}) == []
    assert len(calls) == 1


def test_the_callers_variables_are_not_mutated() -> None:
    variables = {"startTime": 0, "code": "abc"}

    def execute(query: str, passed: dict[str, Any]) -> dict[str, Any]:
        return {"reportData": {"report": {"events": {"data": [], "nextPageTimestamp": None}}}}

    fetch_all_events(execute, "query", variables)
    assert variables == {"startTime": 0, "code": "abc"}

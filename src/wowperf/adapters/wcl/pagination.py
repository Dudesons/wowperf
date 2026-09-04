# ABOUTME: Follows the events cursor until exhausted, collecting every page into one list.
# ABOUTME: Warcraft Logs pages events by feeding nextPageTimestamp back as the next startTime.

from collections.abc import Callable
from typing import Any

from wowperf.adapters.wcl.errors import WclError

Execute = Callable[[str, dict[str, Any]], dict[str, Any]]


def fetch_all_events(
    execute: Execute, query: str, variables: dict[str, Any]
) -> list[dict[str, Any]]:
    page_variables = dict(variables)
    events: list[dict[str, Any]] = []

    while True:
        payload = execute(query, page_variables)
        try:
            page = payload["reportData"]["report"]["events"]
            events.extend(page["data"])
        except (KeyError, TypeError) as error:
            raise WclError(
                "An events page did not carry reportData.report.events.data as expected"
            ) from error

        cursor = page.get("nextPageTimestamp")
        if cursor is None:
            return events
        page_variables["startTime"] = cursor

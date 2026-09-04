# ABOUTME: Turns whatever a user pastes into a report code and an optional fight ID.
# ABOUTME: Accepts a bare code or a full report URL, with or without a #fight fragment.

import re

REPORT_PATTERN = re.compile(
    r"^(?:https?://[^/]*warcraftlogs\.com/reports/)?(?P<code>[A-Za-z0-9]{6,})"
    r"(?:[/?][^#]*)?(?:#.*?fight=(?P<fight>\d+|last).*)?$"
)


def parse_report_url(value: str) -> tuple[str, int | None]:
    match = REPORT_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(f"{value!r} is not a Warcraft Logs report code or URL")

    fight = match.group("fight")
    return match.group("code"), int(fight) if fight and fight != "last" else None

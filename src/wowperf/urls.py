# ABOUTME: Turns whatever a user pastes into a report code and an optional fight ID.
# ABOUTME: Accepts a bare code or a full report URL, fight given as a query string or fragment.

import re
from urllib.parse import parse_qs, urlsplit

REPORT_PATTERN = re.compile(
    r"^(?:https?://[^/]*warcraftlogs\.com/reports/)?(?P<code>[A-Za-z0-9]{6,})"
    r"(?P<rest>[/?#].*)?$"
)


def _fight_param(query_or_fragment: str) -> int | None:
    """Read a fight=N or fight=last value out of a query string or fragment body."""
    values = parse_qs(query_or_fragment).get("fight")
    if not values:
        return None
    value = values[-1]
    return None if value == "last" else int(value)


def parse_report_url(value: str) -> tuple[str, int | None]:
    match = REPORT_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(f"{value!r} is not a Warcraft Logs report code or URL")

    rest = urlsplit(match.group("rest") or "")

    # A browser's address bar shows the fragment last, so it wins over the query
    # string when a pasted URL somehow carries a fight number in both.
    fight = _fight_param(rest.fragment)
    if fight is None:
        fight = _fight_param(rest.query)
    return match.group("code"), fight

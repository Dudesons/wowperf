# ABOUTME: Turns whatever a user pastes into a report code and fight ID, or a character.
# ABOUTME: Accepts a bare code or a report URL, and a character page URL for the character command.

import re
from typing import NamedTuple
from urllib.parse import parse_qs, unquote, urlsplit

REPORT_PATTERN = re.compile(
    r"^(?:https?://[^/]*warcraftlogs\.com/reports/)?(?P<code>[A-Za-z0-9]{6,})"
    r"(?P<rest>[/?#].*)?$"
)

CHARACTER_PATTERN = re.compile(
    r"^https?://[^/]*warcraftlogs\.com/character/"
    r"(?P<region>[A-Za-z]+)/(?P<realm>[^/?#]+)/(?P<name>[^/?#]+)/?(?P<rest>[?#].*)?$"
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


class CharacterRef(NamedTuple):
    """One character's address on Warcraft Logs, in the form the API's `character` field takes.

    `realm` is the server slug the page's address carries (`argent-dawn`), which
    is what `serverSlug` wants. `name` is percent-decoded, so an accented name
    reaches the API as itself.
    """

    region: str
    realm: str
    name: str
    zone_id: int | None


def parse_character_url(value: str) -> CharacterRef:
    match = CHARACTER_PATTERN.match(value.strip())
    if match is None:
        raise ValueError(
            f"{value!r} is not a Warcraft Logs character URL "
            "(https://www.warcraftlogs.com/character/<region>/<realm>/<name>)"
        )
    rest = urlsplit(match.group("rest") or "")
    zones = parse_qs(rest.query).get("zone")
    zone_id = None
    if zones:
        if not zones[-1].isdigit():
            raise ValueError(f"zone={zones[-1]!r} is not a zone id")
        zone_id = int(zones[-1])
    return CharacterRef(
        region=match.group("region").lower(),
        realm=unquote(match.group("realm")).lower(),
        name=unquote(match.group("name")),
        zone_id=zone_id,
    )

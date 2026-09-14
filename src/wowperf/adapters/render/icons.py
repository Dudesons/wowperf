# ABOUTME: Turns an ability id into the address of its art on the icon CDN.
# ABOUTME: Every rule here decides what may become a URL, and what draws nothing at all.

import re
from collections.abc import Mapping

SAFE_NAME = re.compile(r"[a-z0-9_-]+\.jpg")
"""What the ability dictionary's icon strings look like, and nothing else.

The string comes from an API and lands in a URL on a page that gets shared, so
it is checked before it becomes one. Every one of the 2511 names in a real
report matches this, so the rule refuses nothing that exists today.
"""

CDN_BASE = "https://wow.zamimg.com/images/wow/icons/medium/"
"""Where the report's icons are drawn from.

`medium` is 36x36, which is exactly 2x the 18 CSS pixels they are drawn at, so
they stay crisp on a HiDPI display. The size is a segment of the path rather
than bytes in the page, so changing it costs one re-render and no re-fetch.
"""

UNKNOWN_ABILITY = 0
"""The ability dictionary's own row for an ability it could not name.

It carries a real icon file -- a generic axe -- so drawing it would put art
beside a row nobody identified. It is refused before it becomes an address.
"""


def icon_filename(raw: str) -> str | None:
    """The file an icon string names, or None when it does not name one.

    A handful of strings carry a `?cachebust` suffix over a file the dictionary
    also names plainly, so dropping the query both builds the right URL and
    collapses the two spellings onto one address.
    """
    name = raw.split("?", 1)[0]
    return name if SAFE_NAME.fullmatch(name) else None


class CdnIcons:
    """An ability id, resolved to the address its art is served from.

    Nothing here touches the network or the disk: the page carries addresses and
    the reader's browser resolves them when the report is opened. None means no
    icon for that ability, whatever the reason -- an id the report's dictionary
    does not name, or a name that is not a bare lowercase jpg. The page does the
    same thing for both, so it is told no more.
    """

    def __init__(self, filenames: Mapping[int, str]) -> None:
        self._filenames = filenames

    def url(self, ability_id: int) -> str | None:
        if ability_id == UNKNOWN_ABILITY:
            return None
        raw = self._filenames.get(ability_id)
        if raw is None:
            return None
        name = icon_filename(raw)
        return None if name is None else CDN_BASE + name

# ABOUTME: Turns an ability id into an embedded image, through a permanent store and Blizzard's CDN.
# ABOUTME: Every rule here decides what to fetch, what to keep, and what to draw nothing for.

import os
import re
import tempfile
from pathlib import Path

SAFE_NAME = re.compile(r"[a-z0-9_-]+\.jpg")
"""What the ability dictionary's icon strings look like, and nothing else.

The string comes from an API and becomes both a URL and a path on this machine,
so it is checked before it is either. Every one of the 2511 names in a real
report matches this, so the rule refuses nothing that exists today.
"""


def icon_filename(raw: str) -> str | None:
    """The file an icon string names, or None when it does not name one.

    A handful of strings carry a `?cachebust` suffix over a file the dictionary
    also names plainly, so dropping the query both builds the right URL and
    collapses the two spellings onto one cache entry.
    """
    name = raw.split("?", 1)[0]
    return name if SAFE_NAME.fullmatch(name) else None


class IconStore:
    """Icon bytes on disk, kept for good, one file per icon.

    Never expires. The art does not change, and an expiring store would re-pull
    every icon on a schedule to receive the same bytes back. An absence is
    recorded too, beside the file it stands in for, so an icon Blizzard does not
    serve costs one request ever rather than one per run.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def read(self, name: str) -> bytes | None:
        path = self._directory / name
        return path.read_bytes() if path.is_file() else None

    def known_miss(self, name: str) -> bool:
        return (self._directory / f"{name}.miss").is_file()

    def write(self, name: str, payload: bytes) -> None:
        self._write_atomically(self._directory / name, payload)

    def write_miss(self, name: str) -> None:
        self._write_atomically(self._directory / f"{name}.miss", b"")

    def _write_atomically(self, path: Path, payload: bytes) -> None:
        handle, temporary = tempfile.mkstemp(dir=self._directory)
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(payload)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

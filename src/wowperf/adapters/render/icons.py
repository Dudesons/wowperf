# ABOUTME: Turns an ability id into an embedded image, through a permanent store and Blizzard's CDN.
# ABOUTME: Every rule here decides what to fetch, what to keep, and what to draw nothing for.

import base64
import os
import re
import tempfile
from collections.abc import Callable, Mapping
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


ICON_BASE = "https://render.worldofwarcraft.com/eu/icons/36/"
"""Blizzard's own render CDN, which needs no API key.

Sizes 18, 36 and 56 are served and 128 is not; regions us, eu, kr and tw are
served and cn is not. Thirty-six matches the size these are drawn at.
"""

UNKNOWN_ABILITY = 0
"""The ability dictionary's own row for an ability it could not name.

It carries a real icon file -- a generic axe -- so drawing it would put art
beside a row nobody identified. It is refused before anything is fetched.
"""


class BlizzardIcons:
    """An ability id, drawn as bytes the page carries with it.

    `fetch` is handed in rather than built here so the rules above it can be
    tested without a network. It answers a URL with a status, a content type and
    a body.
    """

    def __init__(
        self,
        filenames: Mapping[int, str],
        store: IconStore,
        fetch: Callable[[str], tuple[int, str, bytes]],
    ) -> None:
        self._filenames = filenames
        self._store = store
        self._fetch = fetch

    def data_uri(self, ability_id: int) -> str | None:
        name = self._name_of(ability_id)
        if name is None:
            return None
        payload = self._store.read(name)
        if payload is None:
            if self._store.known_miss(name):
                return None
            payload = self._download(name)
        if payload is None:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(payload).decode()

    def _name_of(self, ability_id: int) -> str | None:
        if ability_id == UNKNOWN_ABILITY:
            return None
        raw = self._filenames.get(ability_id)
        return None if raw is None else icon_filename(raw)

    def _download(self, name: str) -> bytes | None:
        """An answer counts as an icon only if it says so twice.

        A file Blizzard does not serve comes back as a refusal carrying XML
        rather than as a not-found, so the status alone would have an error
        document embedded in the page as though it were a picture.
        """
        status, content_type, body = self._fetch(ICON_BASE + name)
        if status != 200 or not content_type.startswith("image/"):
            self._store.write_miss(name)
            return None
        self._store.write(name, body)
        return body

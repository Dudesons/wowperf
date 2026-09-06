# ABOUTME: Content-addressed JSON cache for Warcraft Logs responses, stored one file per key.
# ABOUTME: Entries are kept indefinitely, or expire after a maximum age when one is given.

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


def cache_key(query: str, variables: dict[str, Any]) -> str:
    canonical = json.dumps(variables, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{query}\n{canonical}".encode()).hexdigest()


class DiskCache:
    """One JSON file per key. Entries live forever unless a maximum age is given.

    Two policies, one class: report data for a finished fight never changes and
    is kept indefinitely, while leaderboard rows and everything fetched for a
    reference run expire, so that no standing store of other players' logs
    accumulates. The age of an entry is its file's modification time, stamped
    from `now` at write time so a test can drive the clock.
    """

    def __init__(
        self,
        directory: Path,
        max_age_seconds: float | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._directory = directory
        self._max_age = max_age_seconds
        self._now = now
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._max_age is not None:
            self.purge_expired()

    def _expired(self, path: Path) -> bool:
        return self._max_age is not None and self._now() - path.stat().st_mtime > self._max_age

    def purge_expired(self) -> None:
        """Delete every entry older than the maximum age. No-op without one."""
        if self._max_age is None:
            return
        for path in self._directory.glob("*.json"):
            try:
                if self._expired(path):
                    path.unlink(missing_ok=True)
            except OSError:
                # Another process sharing the directory may have removed it
                # first, which is the outcome wanted anyway.
                continue

    def get_or_fetch(self, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self._directory / f"{key}.json"
        if path.exists() and not self._expired(path):
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

        value = fetch()
        self._write_atomically(path, json.dumps(value))
        return value

    def _write_atomically(self, path: Path, text: str) -> None:
        """Write through a temporary neighbour and rename it into place.

        An entry may be read for a day or forever, so a file truncated by a
        process dying mid-write would poison its key for that whole span.
        os.replace is atomic on POSIX and on Windows, and the temporary file
        shares the directory so the rename stays within one filesystem.

        The modification time is stamped from `now` rather than left to the
        filesystem, because the age of an entry is read from it and a test must
        be able to drive that clock.
        """
        handle, temporary = tempfile.mkstemp(dir=self._directory, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.replace(temporary, path)
            stamp = self._now()
            os.utime(path, (stamp, stamp))
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

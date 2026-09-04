# ABOUTME: Content-addressed JSON cache for Warcraft Logs responses, stored one file per key.
# ABOUTME: Report data for a finished fight never changes, so entries are kept indefinitely.

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


def cache_key(query: str, variables: dict[str, Any]) -> str:
    canonical = json.dumps(variables, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{query}\n{canonical}".encode()).hexdigest()


class DiskCache:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def get_or_fetch(self, key: str, fetch: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        path = self._directory / f"{key}.json"
        if path.exists():
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))

        value = fetch()
        self._write_atomically(path, json.dumps(value))
        return value

    def _write_atomically(self, path: Path, text: str) -> None:
        """Write through a temporary neighbour and rename it into place.

        Entries never expire, so a file truncated by a process dying mid-write
        would poison its key for good. os.replace is atomic on POSIX and on
        Windows, and the temporary file shares the directory so the rename
        stays within one filesystem.
        """
        handle, temporary = tempfile.mkstemp(dir=self._directory, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

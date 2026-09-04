# ABOUTME: Content-addressed JSON cache for Warcraft Logs responses, stored one file per key.
# ABOUTME: Report data for a finished fight never changes, so entries are kept indefinitely.

import hashlib
import json
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
        path.write_text(json.dumps(value), encoding="utf-8")
        return value

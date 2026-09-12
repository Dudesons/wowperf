# ABOUTME: Reads the credentials dotfile a clone is told to create, in whatever encoding it has.
# ABOUTME: The only place that knows credentials may come from a file rather than the environment.

import codecs
from collections.abc import MutableMapping
from pathlib import Path

QUOTES = "\"'"


def _decode(raw: bytes) -> str:
    """Text from bytes, trusting the byte order mark over any declared encoding.

    Whoever creates this file creates it with whatever their editor or shell
    defaults to, and on Windows that is often UTF-16: PowerShell's redirect
    and Out-File both write it. Reading such a file as UTF-8 does not raise --
    it yields mojibake and an empty result, which reads as "no credentials"
    and sends the reader looking in the wrong place entirely.
    """
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in QUOTES:
        return value[1:-1]
    return value


def read_dotenv(path: Path) -> dict[str, str]:
    """The `KEY=value` pairs in `path`, or nothing at all when it does not exist.

    A missing file is not an error: the credentials are equally allowed to come
    from the surrounding environment, which is how CI and the end-to-end suite
    supply them.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}

    values: dict[str, str] = {}
    for line in _decode(raw).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        values[key.strip()] = _unquote(value.strip())
    return values


def apply_dotenv(path: Path, environ: MutableMapping[str, str]) -> None:
    """Put the file's pairs into `environ`, leaving any already set alone.

    The environment wins so that an exported value always beats a dotfile left
    behind in the clone.
    """
    for key, value in read_dotenv(path).items():
        environ.setdefault(key, value)

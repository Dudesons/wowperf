# ABOUTME: Pins what `analyze` writes for one compared mock run, byte for byte.
# ABOUTME: Guards the lifting of its pipeline into shared functions: nothing a reader gets may move.

from datetime import datetime, tzinfo
from pathlib import Path
from typing import Self

import pytest

from tests.test_cli import run_analyze

GOLDEN = Path(__file__).parent / "golden" / "analyze"


class _FrozenDatetime(datetime):
    """`datetime` whose clock reads one fixed minute, so the page's fetch line is stable."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 14, 9, 30)


@pytest.mark.parametrize("name", ["abc123-36.findings.json", "abc123-36.html"])
def test_analyze_writes_exactly_what_it_wrote_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytestconfig: pytest.Config, name: str
) -> None:
    monkeypatch.setattr("wowperf.cli.datetime", _FrozenDatetime)

    result = run_analyze(tmp_path, "--player", "Emberkin")

    assert result.exit_code == 0, result.output
    written = (tmp_path / "out" / name).read_text(encoding="utf-8")
    golden = GOLDEN / name
    if pytestconfig.getoption("--golden-update"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(written, encoding="utf-8")
        pytest.skip("golden file rewritten")
    assert written == golden.read_text(encoding="utf-8")

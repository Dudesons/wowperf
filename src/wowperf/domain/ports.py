# ABOUTME: The boundaries of the domain: how it obtains runs and rankings, and emits reports.
# ABOUTME: Protocols only, so the domain never imports an adapter or anything doing I/O.

from pathlib import Path
from typing import Protocol

from wowperf.domain.comparison.reference import ParseRow, SpeedRow
from wowperf.domain.model import Run


class RunRepository(Protocol):
    def get(self, report_code: str, fight_id: int | None) -> Run: ...


class RankingRepository(Protocol):
    def fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]: ...

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str
    ) -> tuple[ParseRow, ...]: ...


class ReportRenderer(Protocol):
    def render(self, html_path: Path, context: dict[str, object]) -> None: ...


class IconSource(Protocol):
    # None means no icon for that ability, whatever the reason -- an id the report's
    # dictionary does not name, a file the CDN does not serve, a store that could not
    # be read. The page does the same thing for all three, so it is told no more.
    def data_uri(self, ability_id: int) -> str | None: ...

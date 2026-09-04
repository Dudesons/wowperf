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

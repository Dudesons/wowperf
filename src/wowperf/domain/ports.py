# ABOUTME: The boundaries of the domain: how it obtains runs and rankings, and emits reports.
# ABOUTME: Protocols only, so the domain never imports an adapter or anything doing I/O.

from pathlib import Path
from typing import Protocol

from wowperf.domain.comparison.mechanics import ReferenceKillRow
from wowperf.domain.comparison.reference import ParseRow, SpeedRow
from wowperf.domain.model import Run


class RunRepository(Protocol):
    def get(self, report_code: str, fight_id: int | None) -> Run: ...


class RankingRepository(Protocol):
    def fastest_runs(self, encounter_id: int, keystone_level: int) -> tuple[SpeedRow, ...]: ...

    def top_parses(
        self, encounter_id: int, keystone_level: int, class_name: str, spec: str
    ) -> tuple[ParseRow, ...]: ...


class EncounterRankingRepository(Protocol):
    """The raid axis, as a sibling of `RankingRepository` rather than a widening of it.

    Two protocols rather than one parameter that expresses both axes: a union
    axis type leaves the wrong axis representable -- a Mythic+ caller can
    construct a raid axis and mypy accepts it -- so the only defence would be a
    runtime guard. Design 14 item 3 rules that out. Here the wrong axis is
    unrepresentable because the method is absent, not because it is guarded.
    """

    def reference_kills(
        self, encounter_id: int, difficulty: int, partition: int
    ) -> tuple[ReferenceKillRow, ...]: ...


class ReportRenderer(Protocol):
    def render(self, html_path: Path, context: dict[str, object]) -> None: ...


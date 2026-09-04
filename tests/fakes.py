# ABOUTME: Test doubles that satisfy the domain ports without touching the network.
# ABOUTME: Lets analyser and service tests run offline against real domain objects.

from wowperf.domain.model import Run


class InMemoryRunRepository:
    """Serves pre-built runs. Satisfies RunRepository."""

    def __init__(self, runs: dict[tuple[str, int | None], Run]) -> None:
        self._runs = runs

    def get(self, report_code: str, fight_id: int | None) -> Run:
        try:
            return self._runs[(report_code, fight_id)]
        except KeyError:
            raise KeyError(f"No run stored for report {report_code} fight {fight_id}") from None

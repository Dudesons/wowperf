# ABOUTME: The phase vocabulary Warcraft Logs names for an encounter, and when each began.
# ABOUTME: Read from the API and never encoded here -- no boss rule lives in this project.

from wowperf.domain.base import Frozen


class Phase(Frozen):
    """One named phase of an encounter, as `PhaseMetadata` reports it.

    The name comes from `Report.phases` at runtime. Design section 3.3 forbids
    encoding a phase table and nothing here encodes one: an encounter the API
    names no phases for simply has none, and every phase claim goes silent.
    """

    id: int
    name: str
    is_intermission: bool = False


class PhaseTransition(Frozen):
    """When one attempt entered a phase, as `PhaseTransition` reports it.

    `start_ms` is milliseconds from report start, the same basis every other
    timestamp in this project uses. The API reports it as a Float and it is
    truncated here rather than rounded, so a transition is never reported as
    having happened later than it did.

    A transition list is not a ladder. One measured attempt ran 1, 2, 1, 2, 1
    (skill file, 2026-09-16), so the highest id reached means progress only on
    an encounter whose `separates_wipes` is true.
    """

    id: int
    start_ms: int

# ABOUTME: The run as a sequence: deaths and casts, each located in time and in a pull.
# ABOUTME: Pure data; analysers derive meaning from these, adapters produce them.

from wowperf.domain.base import Frozen


class Death(Frozen):
    player_name: str
    actor_id: int
    timestamp_ms: int
    killing_blow: str
    overkill: int
    pull_index: int | None = None
    seconds_until_next_action: float | None = None


class CastEvent(Frozen):
    actor_id: int
    ability_id: int
    ability_name: str
    timestamp_ms: int
    pull_index: int | None = None

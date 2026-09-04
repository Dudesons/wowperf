# ABOUTME: Season constants the API does not expose, as a pure value object.
# ABOUTME: Reading them off disk is an adapter's job; this file performs no I/O.

from wowperf.domain.base import Frozen


class SeasonData(Frozen):
    """Timer constants Blizzard retunes between seasons."""

    death_penalty_seconds: float
    death_penalty_seconds_high_key: float
    high_key_threshold: int

    def death_penalty(self, keystone_level: int) -> float:
        """Seconds a single death adds to the keystone timer at this level."""
        if keystone_level >= self.high_key_threshold:
            return self.death_penalty_seconds_high_key
        return self.death_penalty_seconds

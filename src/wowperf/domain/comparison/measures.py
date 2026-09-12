# ABOUTME: The per-ability figures a comparison measures, shared by its findings and its table.
# ABOUTME: One definition of a rate, so a row and the table beneath it cannot disagree.

from enum import StrEnum

from wowperf.domain.base import Frozen


class Verdict(StrEnum):
    """Which branch a compared ability or aura took.

    `UNJUDGED` is reached only by auras: `onSelf` carries no source, so an aura
    we show none of may be a teammate's buff nobody gave this player, and that
    is not the same claim as being below the sample. No cast rate is ever
    unjudged, because a cast is unambiguously the player's own.
    """

    BELOW = "below"
    ABOVE = "above"
    LEVEL = "level"
    UNJUDGED = "unjudged"


class Stretch(StrEnum):
    """Which stretch of the dungeon a rate was measured over.

    The two never share a denominator -- one is boss-pull seconds and the other
    the seconds of trash both routes fought -- so a row carries which it is
    rather than leaving a reader to infer it from the figure.
    """

    BOSS = "boss"
    TRASH = "trash"


class AbilityRate(Frozen):
    """One ability's cast rate against the sample's median, in casts a minute."""

    ability_id: int
    name: str
    ours: float
    their_median: float
    their_rates: tuple[float, ...]
    stretch: Stretch
    verdict: Verdict


class AuraUptime(Frozen):
    """One aura's share of our boss time against the sample's median share.

    Fractions, not seconds: two runs fight the same boss for different long.
    """

    ability_id: int
    name: str
    ours: float
    their_median: float
    their_fractions: tuple[float, ...]
    verdict: Verdict


class PlayerMeasures(Frozen):
    """Everything one player's comparison measured, and the denominators behind it.

    The denominators ride along because a caption has to state them: a rate per
    minute means nothing to a reader who cannot see how many minutes it was
    drawn from.
    """

    boss: tuple[AbilityRate, ...] = ()
    trash: tuple[AbilityRate, ...] = ()
    auras: tuple[AuraUptime, ...] = ()
    boss_seconds: float = 0.0
    trash_seconds: float = 0.0
    pack_count: int = 0

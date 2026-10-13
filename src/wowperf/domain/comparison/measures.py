# ABOUTME: The per-ability figures a comparison measures, shared by its findings and its table.
# ABOUTME: One definition of a rate, so a row and the table beneath it cannot disagree.

from enum import StrEnum

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.boss_debuffs import Withheld
from wowperf.domain.debuffs import PairingTally


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
    """One aura's share of the stretch its family judges, against the sample's median share.

    Fractions, not seconds: two runs fight the same boss for different long.
    """

    ability_id: int
    name: str
    ours: float
    their_median: float
    their_fractions: tuple[float, ...]
    verdict: Verdict


class BossCell(Frozen):
    """One boss's figure in one debuff's row: ours against the sample's, never a verdict.

    `ours` is None only when our own pull of this boss was withheld, and
    `their_median` is None whenever `withheld` names a reason, so a cell
    always says why it is missing a figure.
    """

    encounter_id: int
    boss: str
    ours: float | None = None
    their_median: float | None = None
    withheld: Withheld | None = None


class StretchCell(Frozen):
    """One stretch's figure in a row: ours against the sample's median, never a verdict.

    `ours` is None only when our own side measured nothing over that stretch,
    and `their_median` is None whenever `withheld` names a reason, so a cell
    always says why it is missing a figure.
    """

    ours: float | None = None
    their_median: float | None = None
    withheld: Withheld | None = None


class AuraRow(Frozen):
    """One buff: the figure judged over the whole key clock, and two cells that describe.

    `uptime` is the key clock's figure and carries the verdict. `without_bosses`
    is the key less its boss pulls and `bosses` the boss pulls; neither carries
    a verdict.
    """

    uptime: AuraUptime
    without_bosses: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()


class DebuffReach(Frozen):
    """One debuff's reach over each stretch: the share of enemies it sat on at all.

    Described, never judged: a reach threshold would be invented, not measured.
    `overall_fractions` are the references' Overall reaches above zero, which
    give `overall`'s median; the reach table states their range and count.
    """

    overall: StretchCell = StretchCell()
    trash: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()
    overall_fractions: tuple[float, ...] = ()


class DebuffRow(Frozen):
    """One debuff: the judged figure over every enemy of the key, then what describes it.

    `uptime` is Overall coverage and carries the verdict. `trash` and `bosses`
    describe the two stretches, `cells` each boss, and `reach` the share of
    enemies the debuff sat on at all; none of them carries a verdict.

    `shared_with` names, by actor id, the other players whose copies of this
    debuff replaced this player's rather than sat beside it. When it names
    anyone the row is not judged, whatever `uptime.verdict` says: the figure is
    this player's share of one slot, not their coverage.
    """

    uptime: AuraUptime
    trash: StretchCell = StretchCell()
    bosses: StretchCell = StretchCell()
    cells: tuple[BossCell, ...] = ()
    reach: DebuffReach = DebuffReach()
    shared_with: tuple[int, ...] = ()


class DebuffTable(Frozen):
    """Everything the debuff tables state, with the denominator and the log's own counts.

    `tally` is None only when no stream was read for our side, whether it was
    never requested or could not be read, so that a findings file tells "no
    stream read" apart from "read, and clean". Whenever the stream was read it
    is our own tally, even with no rows to show.
    """

    rows: tuple[DebuffRow, ...] = ()
    seconds: float = 0.0
    """Our summed enemy-alive seconds over every measured enemy: Overall's denominator."""
    bosses: tuple[str, ...] = ()
    tally: PairingTally | None = None
    deathless: int = 0
    """Our council bosses of a kill pull with no death in the log, measured to the pull's end."""
    unmeasured_no_death: int = 0
    """Our enemies debuffed with no death after it in the log: left out of coverage and reach."""
    undebuffed_deaths: int = 0
    """Our enemies that died with no debuff from anyone since their previous death."""


class StatShare(Frozen):
    """One secondary's share of a player's own rating budget, against the sample's.

    A share rather than a rating, because a top parse out-gears the run and so
    carries more of every secondary at once: the raw gap would restate the item
    level confound the report already prints, and would read as "behind on
    everything" whatever the player had chosen. The share is the part a gem, an
    enchant or a kept piece actually moves, and it is what balance means.

    `our_rating` and `their_median_rating` ride along because a reader
    recognises a rating and has to be able to see the figure the share came
    from. The judgement is the share; the rating is the fact beside it.
    """

    name: str
    ours: float
    their_median: float
    their_shares: tuple[float, ...]
    our_rating: int
    their_median_rating: float
    their_ratings: tuple[float, ...]
    verdict: Verdict


class PlayerMeasures(Frozen):
    """Everything one player's comparison measured, and the denominators behind it.

    The denominators ride along because a caption has to state them: a rate per
    minute means nothing to a reader who cannot see how many minutes it was
    drawn from.
    """

    boss: tuple[AbilityRate, ...] = ()
    trash: tuple[AbilityRate, ...] = ()
    auras: tuple[AuraRow, ...] = ()
    stats: tuple[StatShare, ...] = ()
    debuffs: DebuffTable = DebuffTable()
    boss_seconds: float = 0.0
    trash_seconds: float = 0.0
    pack_count: int = 0
    key_seconds: float = 0.0
    """Our key clock in seconds, from the fight's start to its end: the buff table's
    denominator."""

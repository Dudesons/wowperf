# ABOUTME: One report read whole -- every boss as its own Progression -- and that read deepened.
# ABOUTME: Night is the shape, LoadedNight its streams, FailedPull a pull that would not load.

from wowperf.domain.base import Frozen
from wowperf.domain.progression import LoadedProgression, Progression


class Night(Frozen):
    """Every boss a report holds, in the order its fight list gave them.

    A sibling of `Progression` -- that one is a boss's attempts, this one a
    report's bosses.

    `progression` refuses a report with several bosses because its subject is
    one boss and picking one would analyse a fight nobody asked for. This type
    is the same fight list read the other way: the report is the subject, so
    several bosses is the ordinary case rather than the ambiguous one.

    An empty `bosses` is representable on purpose. A report with no boss fights
    at all is a real thing to be handed, and the refusal belongs in the command,
    where it can name the report, rather than in a constructor that can only
    raise.
    """

    report_code: str
    bosses: tuple[Progression, ...] = ()


class FailedPull(Frozen):
    """One pull that could not be deepened, and what stopped it.

    A night is allowed to shrink, never to shrink quietly: a pull whose
    streams fail is dropped from the boss that holds it and named here
    instead, so the page can say which pull is missing and why rather than
    covering fewer pulls than the report it claims to cover.

    `reason` is the failure's own message, not a phrase chosen here. The
    reader is being told what went wrong, and a canned sentence would say
    less than the exception already does.
    """

    fight_id: int
    reason: str


class LoadedNight(Frozen):
    """A `Night` and the pulls that have been deepened.

    `loaded` runs parallel to `night.bosses`, one `LoadedProgression` each and
    in the same order, so a boss whose every attempt was a reset -- or whose
    every attempt failed -- is still present with an empty one. Dropping it
    would lose the fact that the boss was pulled at all, which the page has to
    be able to say.
    """

    night: Night
    loaded: tuple[LoadedProgression, ...] = ()
    failed_pulls: tuple[FailedPull, ...] = ()

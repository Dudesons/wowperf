# ABOUTME: One report read whole: every boss it holds, each as its own Progression.
# ABOUTME: A sibling of Progression -- that one is a boss's attempts, this one a report's bosses.

from wowperf.domain.base import Frozen
from wowperf.domain.progression import Progression


class Night(Frozen):
    """Every boss a report holds, in the order its fight list gave them.

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

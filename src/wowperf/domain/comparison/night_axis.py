# ABOUTME: The one disclosure that a night page draws no parse axis at all, for any pull.
# ABOUTME: A seam, not a calculation -- it states why the axis is missing, once for the page.

from wowperf.domain.findings import Confidence, Finding

NOT_DRAWN_ID = "compare.parse.not_drawn"

NOT_DRAWN_DETAIL = (
    "wowperf night does not draw the parse axis at all: this page never asks a leaderboard "
    "for a comparison, on a kill or on a wipe. Every family that axis carries is absent from "
    "this page as a result: damage against the board, damage by target, casts a minute, "
    "talents, buff uptime, and the percentile. wowperf raid --fight N is what draws them, "
    "for one pull."
)
"""Why the whole page carries no parse axis, once, in place of six silences.

`WITHHELD_DETAIL` in `parse_axis.py` opens by saying the attempt did not kill
the boss, and therefore this report carries no rankings row -- true of a wipe
and false of a night page: a night page omits the axis on kills too, because
the command never draws it. Reusing that sentence here would put the wrong
cause in front of a reader, so this is a distinct sentence with a distinct id,
naming the same six families the raid axis names so a reader who has seen
`raid`'s output can match the two lists.

This is the sentence for a night that compared nothing: one read with
`--no-compare`, or one where no pull loaded to be compared.
"""

NOT_DRAWN_COMPARED_DETAIL = (
    "wowperf night does not draw the parse axis at all: this page never asks a parse "
    "leaderboard for a comparison, on a kill or on a wipe. What it compares against the "
    "execution leaderboard's kills is what hit and killed the raid, each attempt's damage "
    "pace, and each kill's time. Every family the parse axis carries is absent from this page "
    "as a result: damage against the board, damage by target, casts a minute, talents, buff "
    "uptime, and the percentile. wowperf raid --fight N is what draws them, for one kill."
)
"""`NOT_DRAWN_DETAIL` for a night that compared its pulls against the reference kills.

Such a night did ask a leaderboard, the execution board, for its reference
kills, so "never asks a leaderboard" and "no comparison against other kills"
would both be false on it. It names what the night does compare against those
kills, so the parse axis's absence is not read as the absence of every
comparison. The parse half stays, and so do the six families and the pointer
to `raid` -- which draws them for one kill, not one pull: on a wipe `raid`
withholds all six, which is also what this night's own wipe pulls say on their
cards.

It is also each compared kill's own parse line, on its cards and its Damage
tab: `WITHHELD_DETAIL` opens by saying the boss lived, false of a kill.
"""

TITLE = "No comparison against other kills is drawn on this page"
COMPARED_TITLE = "No parse comparison is drawn on this page"


def parse_axis_not_drawn(*, compared: bool = False) -> Finding:
    """The disclosure, worded for whether this night compared any pull against the kills.

    `compared` is True when the night was handed any pace sample at all, even
    one every pull then withheld: handing one means a leaderboard was asked.
    """
    return Finding(
        id=NOT_DRAWN_ID,
        title=COMPARED_TITLE if compared else TITLE,
        detail=NOT_DRAWN_COMPARED_DETAIL if compared else NOT_DRAWN_DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("wowperf night never queries a parse leaderboard",),
    )

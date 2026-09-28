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

This is the sentence for a night that compared nothing: read with
`--no-compare`, or holding no wipe to compare.
"""

NOT_DRAWN_PACE_DETAIL = (
    "wowperf night does not draw the parse axis at all: this page never asks a parse "
    "leaderboard for a comparison, on a kill or on a wipe. The one comparison it draws is "
    "each wipe's damage pace against the execution leaderboard's kills. Every family the "
    "parse axis carries is absent from this page as a result: damage against the board, "
    "damage by target, casts a minute, talents, buff uptime, and the percentile. wowperf "
    "raid --fight N is what draws them, for one pull."
)
"""`NOT_DRAWN_DETAIL` for a night that compared its wipes' pace.

Such a night did ask a leaderboard, the execution board, for its reference
kills, so "never asks a leaderboard" and "no comparison against other kills"
would both be false on it. The parse half stays as it was, and so do the six
families and the pointer to `raid`.
"""

TITLE = "No comparison against other kills is drawn on this page"
PACE_TITLE = "No parse comparison is drawn on this page"


def parse_axis_not_drawn(*, pace_compared: bool = False) -> Finding:
    """The disclosure, worded for whether this night compared any wipe's pace.

    `pace_compared` is True when the night was handed any pace sample at all,
    even one every wipe then withheld: handing one means a leaderboard was asked.
    """
    return Finding(
        id=NOT_DRAWN_ID,
        title=PACE_TITLE if pace_compared else TITLE,
        detail=NOT_DRAWN_PACE_DETAIL if pace_compared else NOT_DRAWN_DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("wowperf night never queries a parse leaderboard",),
    )

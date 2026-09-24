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

`compare_parse_axis.WITHHELD_DETAIL` says a wipe carries no rankings row, which
is true of a wipe and false of a night page: a night page omits the axis on
kills too, because the command never draws it. Reusing that sentence here
would put the wrong cause in front of a reader, so this is a distinct sentence
with a distinct id, naming the same six families the raid axis names so a
reader who has seen `raid`'s output can match the two lists.
"""


def parse_axis_not_drawn() -> Finding:
    return Finding(
        id=NOT_DRAWN_ID,
        title="No comparison against other kills is drawn on this page",
        detail=NOT_DRAWN_DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("wowperf night never queries a parse leaderboard",),
    )

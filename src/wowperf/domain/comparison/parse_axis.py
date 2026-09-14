# ABOUTME: The external frame of one raid boss fight: every comparison that needs other kills.
# ABOUTME: A seam, not a calculation -- it binds the raid counting rules and calls, in order.

from collections.abc import Sequence

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.comparison.raid_reference import RaidParseRow, ReportRankings
from wowperf.domain.comparison.sample import ParseSample, find_player
from wowperf.domain.comparison.spells import (
    compare_spells_sample,
    compare_talents,
    whole_fight_casts,
)
from wowperf.domain.comparison.targets import TargetRow, compare_targets
from wowperf.domain.comparison.throughput import compare_damage_total, compare_rank
from wowperf.domain.comparison.uptime import compare_uptime_sample, whole_fight_uptime
from wowperf.domain.comparison.wording import RAID
from wowperf.domain.events import CastEvent
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.model import Player

UNAVAILABLE_ID = "compare.parse.unavailable"

NO_ROUTE: tuple[()] = ()
"""The route a raid boss fight has.

Named rather than written as a bare `()` at four call sites, because what it
says is a fact about raids and not an omission: `whole_fight_casts` and
`whole_fight_uptime` both take a route and ignore it, and this is the route
they ignore.
"""

WITHHELD_DETAIL = (
    "This attempt did not kill the boss. Warcraft Logs ranks kills alone, so this report "
    "carries no rankings row and no leaderboard sample stands beside it, and every "
    "comparison that reads one is withheld together: damage against the board, damage by "
    "target, casts a minute, talents, buff uptime, and the percentile. Nothing is quietly "
    "absent below -- there was no outside reference to compare this attempt against."
)
"""Why six comparisons produced nothing, once, in place of six silences.

Design 13's first risk is that a reader expects an external comparison on a
wipe and reads its absence as a clean result. So the frame is withheld as one
finding that names every family it stands in for, rather than as an empty list
or as six separate notes a reader would have to collect.
"""


def _withheld(our_name: str) -> Finding:
    return Finding(
        id=UNAVAILABLE_ID,
        title=f"No comparison against other kills is available for {our_name}",
        detail=WITHHELD_DETAIL,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("this report carries no rankings row for this fight",),
    )


def _no_sample(our_name: str) -> Finding:
    """The boss died and the leaderboard offered nobody to stand beside us.

    Worded so it cannot be mistaken for the wipe above: the three families that
    read a sample of other players' logs are the ones withheld, and the three
    that read this report's own rankings ran and are on the page.
    """
    return Finding(
        id=UNAVAILABLE_ID,
        title=f"No ranked parse was available for {our_name}",
        detail=(
            "The parse leaderboard returned no reference kills for this specialisation at "
            "this difficulty, so casts a minute, talents and buff uptime are not compared. "
            "The percentile and the damage comparisons beside this one read this report's "
            "own rankings rather than a sample, and are unaffected."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("the parse sample carried no members",),
    )


def compare_parse_axis(
    our_player: Player,
    our_name: str,
    our_seconds: float,
    our_casts: tuple[CastEvent, ...],
    our_auras: PlayerAuras | None,
    sample: ParseSample,
    standing: ReportRankings | None,
    boss_standing: ReportRankings | None,
    board: tuple[RaidParseRow, ...],
    boss_board: tuple[RaidParseRow, ...],
    our_targets: tuple[TargetRow, ...],
    their_targets: Sequence[tuple[TargetRow, ...]],
) -> list[Finding]:
    """Every comparison a raid boss fight draws from outside itself, unranked.

    A seam and not a calculation: nothing here measures anything, sorts
    anything or re-badges anything. `rank_raid_findings` orders what comes back,
    in `analyse_encounter`, which is the one place raid findings are ranked.

    `standing` and `boss_standing` are this report's own rankings rows for the
    two metrics -- the whole containers, not our row out of them, because
    `compare_rank` has to tell "no rankings row at all, because this was a
    wipe" from "a row exists and this player is not in it", and those two say
    different things to a reader. `compare_damage_total` reads only our own row,
    so it is handed exactly that.

    Both raid counting rules are bound here, and this is the only place they
    are: `whole_fight_casts` is what makes a raid cast count at all, because a
    raid cast carries no pull index and the Mythic+ rule would count every
    ability zero times without raising, and `whole_fight_uptime` is its
    counterpart for an aura.

    Six calls covering the seven families design section 6 lists for this axis:
    `compare_spells_sample` answers both 6.3, the cast rates, and 6.4, the casts
    a reference made that we never did. They are called in section 6's order but
    for the percentile, which is emitted last for the reason given at the call.

    `words=RAID` is bound beside each raid rule and never apart from it: a
    sentence naming boss pulls, trash or a keystone level is false of a raid
    fight, and the two arguments are what keep the rule and the sentence about
    it saying the same thing.
    """
    if standing is None:
        return [_withheld(our_name)]

    findings: list[Finding] = [
        *compare_damage_total(
            standing.player_named(our_name),
            boss_standing.player_named(our_name) if boss_standing is not None else None,
            board,
            boss_board,
            our_name,
        ),
        *compare_targets(our_targets, their_targets, our_name),
    ]

    top = sample.top
    if top is None:
        findings.append(_no_sample(our_name))
    else:
        findings += compare_spells_sample(
            NO_ROUTE, our_seconds, our_casts, our_player, our_name, sample,
            counted=whole_fight_casts, words=RAID,
        )
        findings += compare_talents(
            our_player, our_name, find_player(top.players, top.character_name), top
        )
        findings += compare_uptime_sample(
            NO_ROUTE, our_seconds, our_auras, our_name, sample,
            measured=whole_fight_uptime, words=RAID,
        )

    # Last, and not third. Every `compare` finding carries `seconds_lost=None`,
    # so `rank_raid_findings` ties across the whole family and leaves the order
    # this list was built in -- which makes the seam's own order the page's
    # order. Section 6.7 says a percentile is triage and never a headline, so
    # it goes below everything that says what the triage was about.
    findings += compare_rank(standing, boss_standing, our_name)
    return findings

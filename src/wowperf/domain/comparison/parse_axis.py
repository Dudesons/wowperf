# ABOUTME: The external frame of one raid boss fight: every comparison that needs other kills.
# ABOUTME: A seam, not a calculation -- it binds the raid counting rules and calls, in order.

from collections.abc import Sequence

from pydantic import Field

from wowperf.domain.auras import PlayerAuras
from wowperf.domain.base import Frozen
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


class ParseSubject(Frozen):
    """One player to measure against the world, and everything that measurement reads.

    A sibling of `service.ComparisonSubject`, not a reuse of it: that one
    carries a slug, because a Mythic+ comparison re-mints every finding id with
    the player it is about so a report card can be matched by it. A raid finding
    keeps its plain id and names the player in its title instead, so there is no
    slug here to be minted, stamped or left empty by mistake.

    Every field but the player is what an adapter fetched, arriving as a value:
    the domain performs no I/O, and each of these is one query somebody paid for.
    An empty default is the honest reading of "not fetched" for all of them --
    `compare_parse_axis` says so in the tool's own words rather than treating an
    empty sample as a clean result.
    """

    player: Player
    display_name: str = Field(min_length=1)
    our_auras: PlayerAuras | None = None
    sample: ParseSample = ParseSample()
    board: tuple[RaidParseRow, ...] = ()
    boss_board: tuple[RaidParseRow, ...] = ()
    our_targets: tuple[TargetRow, ...] = ()
    their_targets: tuple[tuple[TargetRow, ...], ...] = ()


def _no_specialisation(our_name: str, class_name: str) -> Finding:
    """The log records no specialisation, so no leaderboard could be asked for one.

    A separate absence from `_no_sample`, and it must not be reported as one:
    there, a board was queried and answered with nothing; here, no board was
    queried at all, because a specialisation is what one is queried for. Saying
    "the leaderboard returned no reference kills" of a query never issued would
    be a sentence that is false of the thing it names.

    The percentile is not withheld with the rest: `compare_rank` reads this
    report's own rankings row, which names a player by name and needs no
    specialisation, so it still runs and this sentence says so.
    """
    return Finding(
        id=UNAVAILABLE_ID,
        title=f"No comparison against other kills is available for {our_name} ({class_name})",
        detail=(
            "This log records no specialisation for this player, so no parse leaderboard "
            "could be asked for one: damage against the board, damage by target, casts a "
            "minute, talents and buff uptime are not compared. The percentile beside this "
            "one reads this report's own rankings rather than a leaderboard, and is "
            "unaffected."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=("this log records no specialisation for this player",),
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

    `our_name` is what every sentence shows a reader and is never what a row is
    found by: it is `display_names`' spelling, which two roster members sharing
    a name turn into `Emberkin (actor 693)`, and a rankings row carries the
    plain name. Both joins therefore read `our_player.name`, and both keep
    `our_name` for the sentence.

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

    Three shapes short-circuit, and each says something different: a wipe has no
    external frame at all, a player with no recorded specialisation has no
    leaderboard to be asked for, and a kill whose leaderboard answered with
    nobody still keeps the three families that read this report's own rankings.
    """
    if standing is None:
        return [_withheld(our_name)]

    # After the wipe, because a wipe withholds the percentile too and is the
    # larger truth about the attempt; before everything that reads a board or a
    # sample, because a specialisation is what either is drawn for.
    if not our_player.spec:
        return [
            _no_specialisation(our_name, our_player.class_name),
            *compare_rank(standing, boss_standing, our_name, our_player.name),
        ]

    findings: list[Finding] = [
        *compare_damage_total(
            # `our_player.name` and never `our_name`: a rankings row carries the
            # plain character name, and `our_name` is the spelling
            # `display_names` rewrites to `Emberkin (actor 693)` when two roster
            # members share a name -- which twenty players make ordinary. Joined
            # on the shown spelling, both of those players are told the boss was
            # never killed, on a kill, beside families that compared fine.
            standing.player_named(our_player.name),
            boss_standing.player_named(our_player.name) if boss_standing is not None else None,
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
    findings += compare_rank(standing, boss_standing, our_name, our_player.name)
    return findings

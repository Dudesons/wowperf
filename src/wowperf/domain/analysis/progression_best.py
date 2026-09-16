# ABOUTME: Layer 3: what the deepest attempt did differently, by internal comparison only.
# ABOUTME: It names differences and explains none -- the anatomy is `wowperf raid --fight N`.

from statistics import median

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding
from wowperf.domain.progression import LoadedProgression

MIN_OTHER_ATTEMPTS = 2
"""Below this the deepest attempt has no cluster to stand against.

A median of one figure is that figure, and "the best attempt had fewer deaths
than the one other attempt" is an anecdote wearing a comparison's words. The
keystone comparison falls back below three comparable references for the same
reason.
"""


def raid_invocation(one: LoadedEncounter) -> str:
    """The command that renders this attempt's anatomy, spelled out for a reader.

    Section 5.3: this layer names differences and does not explain them, and
    where a reader wants the anatomy the finding carries the invocation that
    renders it. The progression page never draws one fight's internals itself
    (section 8), so this string is the whole of the hand-off.
    """
    return f"wowperf raid {one.encounter.report_code} --fight {one.encounter.fight_id}"


def roster_deaths(one: LoadedEncounter) -> int:
    """How many roster players died in this attempt.

    Filtered to `one.players` for the reason `_first_death_ms` filters: a pet
    or an unidentified actor dying is not a roster player's death, and letting
    one through would make this figure disagree with the collapse window's
    anchor about what a death is.
    """
    roster_ids = {player.actor_id for player in one.players}
    return sum(1 for death in one.deaths if death.actor_id in roster_ids)


def best_deaths(series: LoadedProgression) -> Finding | None:
    """How many deaths the deepest attempt took, against the median of the rest.

    Deaths, not players, and the title says so. A battle-rezzed player dies
    twice, so on a real night this count runs past the roster size -- measured
    2026-09-16 on a twenty-player night whose deepest attempt logged 21 -- and
    a title phrased as players lost would state an impossibility.

    `measured`: both figures are counts of logged deaths, and the median is
    arithmetic over them. The comparison is internal -- the night against
    itself -- so no reference run and no external sample takes any part in it.

    Withheld below `MIN_OTHER_ATTEMPTS` others, and when nothing was deepened.
    Never withheld for being unflattering: an attempt that went deepest while
    taking more deaths than the rest is a real difference and is stated in
    those words.
    """
    deepest = series.deepest_loaded
    if deepest is None:
        return None

    others = [
        one
        for one in series.attempts_with_events
        if one.encounter.fight_id != deepest.encounter.fight_id
    ]
    if len(others) < MIN_OTHER_ATTEMPTS:
        return None

    mine = roster_deaths(deepest)
    theirs = median(roster_deaths(one) for one in others)
    gap = theirs - mine

    if gap > 0:
        title = f"The best attempt took {mine} roster deaths against a median of {theirs:.0f}"
    elif gap < 0:
        title = (
            f"The best attempt took {mine} roster deaths -- {-gap:.0f} more "
            f"than the median of {theirs:.0f}"
        )
    else:
        title = f"The best attempt took {mine} roster deaths, no difference from the rest"

    return Finding(
        id="progression.best.deaths",
        title=title,
        detail=(
            f"Counted across the {len(others)} other deepened attempts, whose median was "
            f"{theirs:.0f} roster deaths. A median and a range, never an average. This "
            "counts deaths and says nothing about what caused them; to see that attempt's "
            "anatomy -- the health curves, what hit whom, and what each player still had "
            f"-- run `{raid_invocation(deepest)}`."
        ),
        confidence=Confidence.MEASURED,
        evidence=(
            f"{mine} roster deaths on the deepest attempt, fight {deepest.encounter.fight_id}",
            f"median {theirs:.0f} across {len(others)} other attempts",
        ),
    )


# ABOUTME: Layer 3: what the deepest attempt did differently, by internal comparison only.
# ABOUTME: It names differences and explains none -- the anatomy is `wowperf raid --fight N`.

from statistics import median

from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import Confidence, Finding, quantity
from wowperf.domain.model import Player
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


MAX_SURVIVORS = 5
"""At six the finding stops being a difference and starts being the roster.

So at six the finding is withheld, not trimmed to five. Naming the top five out
of a dozen would print a list that reads as the whole difference while the
condition that makes it meaningless -- that nearly everyone came through --
goes unmentioned, which is the one failure a cap can turn into a quiet lie.
"""


def _spec_label(player: Player) -> str:
    """"Frost DeathKnight", not "Frost Death Knight".

    `class_name` is the API's own `subType` (`ingest.py`), which carries no
    space. A test asserting the spaced spelling asserts a string this code
    cannot produce.
    """
    return f"{player.spec} {player.class_name}"


def _specs_that_died(one: LoadedEncounter) -> set[str]:
    """Which specialisations lost at least one player in this attempt."""
    by_actor = {player.actor_id: player for player in one.players}
    return {
        _spec_label(by_actor[death.actor_id])
        for death in one.deaths
        if death.actor_id in by_actor
    }


def best_survived(series: LoadedProgression) -> Finding | None:
    """Specialisations that usually died and did not, on the attempt that went deepest.

    Counted only over specialisations on the deepest attempt's own roster: a
    specialisation that was not there did not survive anything, and a swap out
    reads identically to a survival in a log that records deaths rather than
    lives.

    `derived` rather than `measured`. Not dying is not the same as surviving
    something: a player who stood further out, a healer who was dead already in
    the other attempts and so could not die again, and a raid that reached a
    phase that ability never fires in all produce this shape, and the log
    distinguishes none of them.

    Withheld below `MIN_OTHER_ATTEMPTS` others, when nothing was deepened, and
    when nothing qualifies -- "usually" means more than half of the others,
    strictly, so a specialisation dying in exactly half is not named. Withheld
    again above `MAX_SURVIVORS`, at the other end: a night where most of the
    raid came through the best attempt has no difference to name, and saying so
    by staying silent is honest where naming five of twelve would not be.
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

    candidates = {_spec_label(player) for player in deepest.players} - _specs_that_died(deepest)

    counts: dict[str, int] = {}
    for one in others:
        for spec in _specs_that_died(one) & candidates:
            counts[spec] = counts.get(spec, 0) + 1

    qualifying = [(spec, count) for spec, count in counts.items() if count > len(others) / 2]
    if not qualifying or len(qualifying) > MAX_SURVIVORS:
        return None

    qualifying.sort(key=lambda pair: (-pair[1], pair[0]))
    lines = tuple(
        f"{spec} died in {count} of the {len(others)} other attempts, and not in the best one"
        for spec, count in qualifying
    )

    return Finding(
        id="progression.best.survived",
        title=(
            f"{quantity(len(qualifying), 'specialisation', 'specialisations')} that usually died "
            "came through the best attempt"
        ),
        detail=(
            "Counted across the deepest attempt's own roster, so a specialisation that was "
            "not in the raid for it is never named: "
            + "; ".join(lines)
            + ". Not dying is not the same as surviving something -- standing further out, "
            "being dead already when the others ended, and reaching a phase an ability never "
            "fires in all look like this, and the log tells them apart from none of the "
            "others. That is why this reads as derived. This counts specialisations and "
            "names no player; to see what the best attempt actually looked like, run "
            f"`{raid_invocation(deepest)}`."
        ),
        confidence=Confidence.DERIVED,
        evidence=lines,
    )

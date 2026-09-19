# ABOUTME: Whether an attempt failed because the raid died or because it ran out of damage.
# ABOUTME: An inferred reading of our own attempt, never a comparison of one raid against another.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.statistics import median
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death, Resurrection
from wowperf.domain.findings import Confidence, Finding, FindingFact

WITHHELD_ID = "wipe.cause.withheld"
"""The verdict declined to judge, and this says which of its reasons applied.

`classify_attempt` returned a bare `None` for five different situations until
2026-09-19, and `analyse_encounter` dropped it, so a reader saw no verdict and
could not tell a comparison that was refused from one nobody asked for. Design
section 8.3 wants the withheld case recorded rather than dropped, and this is
the finding that records it. Modelled on `compare.parse.unavailable`, which is
the same shape one layer out: measured, because the absence itself is a fact
about the report rather than a reading of it.

A kill is the one case that still returns nothing, because a kill has no wipe
to explain and a line saying so would be noise on every successful page.
"""

NO_REFERENCE_SAMPLE = (
    "No reference kills were drawn for this boss, so this attempt's duration and "
    "death toll have nothing to be read against. A run made with --no-compare "
    "reaches this, and so does a boss whose leaderboard returned nothing."
)

NO_BOSS_HEALTH = (
    "This report records no boss health for this attempt, so how close it came is "
    "unknown and neither reading can be reached."
)

NO_ROSTER = (
    "This report records no raid roster for this attempt, so the share of it that "
    "died cannot be worked out."
)

NEITHER_SHAPE = (
    "This attempt matched neither shape: the raid was neither taken apart nor left "
    "intact against a boss that held. Naming one of the two here would be a guess."
)

DISMANTLED_SHARE = 0.5
"""Half the raid dead or more is a raid that was taken apart, not one that slipped.

At twenty players a wipe with ten dead has lost its healers' mana, its
battle-resurrections and most of its damage, and no reading of the damage
figures survives that.
"""

INTACT_SHARE = 0.8
"""Four in five still standing is a raid that held. Below this, neither reading is clean."""

WALL_HEALTH = 20.0
"""Boss health above this at the end is a boss that was never close to dying."""

ORDERING_MARGIN = 0.1
"""How far off the attempt's midpoint the deaths' median must sit to settle the order.

A median a millisecond either side of the midpoint settles nothing, and printing
"the deaths came first" off it would be the confident guess the confidence
badges exist to prevent. A tenth of the attempt on each side is the band inside
which the deaths straddle the midpoint rather than concentrate before or after
it; inside it the ordering clause is withheld, the same habit the comparison
axes keep when their samples are too thin.
"""


def _withheld(detail: str, evidence: str) -> Finding:
    """One reason the verdict declined to judge, as a finding a page can print.

    `Confidence.MEASURED` because every one of these is a fact about what the
    report carried, not a reading of the fight: either a field is absent or a
    sample was never drawn, and both are checked rather than inferred. The one
    case that is a judgement -- an attempt matching neither shape -- is still
    measured in the same sense, because what is being stated is that the two
    thresholds were evaluated and neither was met.
    """
    return Finding(
        id=WITHHELD_ID,
        title="No verdict on why this attempt ended",
        detail=detail,
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=(evidence,),
    )


class AlivePoint(Frozen):
    """How many were standing, from this moment until the next point."""

    timestamp_ms: int
    alive: int


def alive_over_time(
    size: int, deaths: tuple[Death, ...], resurrections: tuple[Resurrection, ...]
) -> tuple[AlivePoint, ...]:
    """The raid's headcount as a step function, deaths down and rezzes up.

    One computation behind both the chart and the verdict's own "N of 20 alive
    at the end": two implementations of a rule involving battle resurrections
    would eventually end on different numbers, in two places on one page a
    reader sees at once.

    A resurrection sharing a death's timestamp is ordered before it, so a rez
    landing at the same instant as a death is a no-op and the death is what
    takes effect -- a rez cannot land on somebody who has not died yet, which
    is the rule `_alive_at_the_end` already applies.

    This is a floor on the living, not a reading of them. A player who
    releases and runs back leaves no record at all, so every figure drawn from
    it carries a `derived` badge.
    """
    steps = [(one.timestamp_ms, 0, +1) for one in resurrections]
    steps += [(death.timestamp_ms, 1, -1) for death in deaths]
    steps.sort()

    points = [AlivePoint(timestamp_ms=0, alive=size)]
    alive = size
    for timestamp_ms, _, delta in steps:
        alive = max(0, min(size, alive + delta))
        points.append(AlivePoint(timestamp_ms=timestamp_ms, alive=alive))
    return tuple(points)


def _alive_at_the_end(
    size: int, deaths: tuple[Death, ...], resurrections: tuple[Resurrection, ...]
) -> int:
    """How many of the raid were standing when the attempt ended.

    Design section 8.2's first evidence item, read as it is written. A player
    brought back after their last death is standing again, so counting everyone
    who ever died as dead under-counts the living on any attempt a
    battle-resurrection landed in. `progression_best.best_deaths` records the
    same fact from the other side: a rezzed player dies twice, and one measured
    night logged 21 deaths across twenty players.

    One assumption survives, which is why the fact this feeds is badged
    `derived` rather than measured: a player who released and ran back leaves no
    record at all -- `Resurrection`'s own docstring -- so this is a floor on the
    living rather than a reading of them. It errs in the same direction the
    unreconstructed count did, and by far less.

    `died` stays a count of players who died at any point, and `DISMANTLED_SHARE`
    stays measured against it: a raid that lost ten people and rezzed eight of
    them was still taken apart, which is exactly what that constant's own
    docstring says it is reading.
    """
    return alive_over_time(size, deaths, resurrections)[-1].alive


def _ordering_clause(encounter: Encounter, deaths: tuple[Death, ...]) -> str:
    """Which of the two failures came first, where the deaths' own timing settles it.

    Design section 8.3 asks a both-verdict to say which came first, and when the
    deaths fell is the only reading of order the log supports. Their median is
    measured against the attempt's own midpoint: concentrated in the first half,
    the raid came apart before the damage question could be settled;
    concentrated in the second, the attempt was already long while the raid
    still stood. An enrage wipe -- everyone dead in the last seconds of a long
    attempt -- is the second shape, and a constant sentence naming the deaths
    first had it exactly backwards there.

    Deaths straddling the midpoint settle neither, and the clause is then
    omitted rather than guessed at.
    """
    span = encounter.end_ms - encounter.start_ms
    if not deaths or span <= 0:
        return ""

    middle = median([float(death.timestamp_ms) for death in deaths])
    share = (middle - encounter.start_ms) / span
    if share <= 0.5 - ORDERING_MARGIN:
        return (
            " The deaths came first: their median fell in the attempt's first half, "
            "and a raid this far down cannot make the damage."
        )
    if share >= 0.5 + ORDERING_MARGIN:
        return (
            " The damage came up short before the raid did: the deaths' median fell "
            "in the attempt's second half."
        )
    return ""


def classify_attempt(
    encounter: Encounter,
    deaths: tuple[Death, ...],
    sample: MechanicsSample,
    *,
    resurrections: tuple[Resurrection, ...] = (),
) -> Finding | None:
    """Why this attempt ended, when the log supports saying.

    The only `inferred` finding this area mints, because it is the only
    judgement. The four facts behind it -- three measured, one derived --
    are stated in the finding rather than summarised, so a reader who
    disagrees can see what it read.

    It withholds rather than guesses. A wipe where the raid mostly stood and
    the boss was nearly dead is neither an execution failure nor a wall, and
    the honest answer is to say nothing -- the same habit the comparison axes
    keep when their samples are too thin. The both-verdict's ordering clause
    keeps the same habit one level down: it is measured from when the deaths
    fell, and omitted where that does not settle the question.

    Boss health is `boss_percentage`, never `fight_percentage`. The two are
    different quantities and diverged 51.12 against 3.76 on one measured
    attempt.
    """
    if encounter.kill:
        return None
    if not sample.members:
        return _withheld(NO_REFERENCE_SAMPLE, "no reference kills were drawn")
    if encounter.boss_percentage is None:
        return _withheld(NO_BOSS_HEALTH, "the report carried no boss health")

    size = encounter.size or len(encounter.players)
    if size <= 0:
        return _withheld(NO_ROSTER, "the report carried no roster")

    died = len({death.actor_id for death in deaths})
    # `ReferenceKillRow.deaths` counts death events, measured 2026-09-18 against
    # twelve reference fights: on the four where somebody died twice, the row's
    # figure matched the event count and not the count of distinct players. So
    # the reference median can only be met with an event count. `died` stays a
    # count of players, because the roster share and `DISMANTLED_SHARE` both
    # ask what fraction of the raid was lost, and a raid cannot lose more
    # members than it has.
    death_events = len(deaths)
    alive = _alive_at_the_end(size, deaths, resurrections)
    reference_seconds = median([member.row.duration_seconds for member in sample.members])
    reference_deaths = median([float(member.row.deaths) for member in sample.members])

    dismantled = died / size >= DISMANTLED_SHARE
    stalled = (
        encounter.boss_percentage > WALL_HEALTH
        and encounter.duration_seconds >= reference_seconds
    )

    if dismantled and stalled:
        headline = "both: the raid came apart, and the damage never caught up"
        story = (
            f"{died} of {size} died, and the attempt still ran "
            f"{encounter.duration_seconds:.0f}s against the reference kills' "
            f"{reference_seconds:.0f}s with {encounter.boss_percentage:.1f}% boss health "
            "left."
        ) + _ordering_clause(encounter, deaths)
    elif dismantled:
        headline = "execution: the raid was taken apart"
        # The second clause appears only where the two counts differ, which is
        # where a battle rez put somebody in the tally twice. Stating it on
        # every attempt would print the same number twice in one sentence.
        toll = (
            f"{died} of {size} died"
            if death_events == died
            else f"{died} of {size} died and {death_events} deaths were logged"
        )
        story = (
            f"{toll}, against a median of {reference_deaths:.0f} across "
            "the reference kills. This attempt ended before the damage question could "
            "be asked."
        )
    elif stalled and alive / size >= INTACT_SHARE:
        headline = "throughput: the raid held and the damage was not enough"
        # This branch admits a raid that lost up to a fifth of itself, so the
        # design's own sentence for it -- "nobody died and it still was not
        # enough" -- is true of the branch's cleanest case and false of the
        # rest. It is kept where it holds and replaced where it does not,
        # rather than stated over the whole branch: `mechanics.lethal.*` names
        # the abilities that killed those players on the same page.
        story = (
            f"{alive} of {size} were still alive, and the boss finished on "
            f"{encounter.boss_percentage:.1f}% health after "
            f"{encounter.duration_seconds:.0f}s against the reference kills' "
            f"{reference_seconds:.0f}s. "
        ) + (
            "Nobody died and it still was not enough."
            if died == 0
            else "The raid held together and it still was not enough."
        )
    else:
        return _withheld(NEITHER_SHAPE, "neither shape fit this attempt")

    return Finding(
        id="wipe.cause",
        title=f"This attempt failed on {headline}",
        detail=story,
        confidence=Confidence.INFERRED,
        evidence=(
            f"{alive} of {size} alive at the end",
            f"{encounter.boss_percentage:.1f}% boss health remaining",
            f"{encounter.duration_seconds:.0f}s against a reference median of "
            f"{reference_seconds:.0f}s",
            # Both sides of this comparison are death events. The line still
            # names the players too, because "13 deaths" alone leaves a reader
            # to guess whether thirteen raiders died or fewer died twice.
            f"{death_events} deaths among {died} of our players, against a "
            f"reference median of {reference_deaths:.0f} deaths",
        ),
        facts=(
            FindingFact(
                label="Alive at the end",
                value=f"{alive} of {size}",
                confidence=Confidence.DERIVED,
            ),
            FindingFact(label="Boss health left", value=f"{encounter.boss_percentage:.1f}%"),
            FindingFact(
                label="Our duration",
                value=f"{encounter.duration_seconds:.0f}s",
            ),
            FindingFact(
                label="Reference duration",
                value=f"{reference_seconds:.0f}s median",
                confidence=Confidence.DERIVED,
            ),
        ),
    )

# ABOUTME: Whether an attempt failed because the raid died or because it ran out of damage.
# ABOUTME: An inferred reading of our own attempt, never a comparison of one raid against another.

from wowperf.domain.comparison.mechanics import MechanicsSample
from wowperf.domain.comparison.statistics import median
from wowperf.domain.encounter import Encounter
from wowperf.domain.events import Death
from wowperf.domain.findings import Confidence, Finding, FindingFact

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


def classify_attempt(
    encounter: Encounter,
    deaths: tuple[Death, ...],
    sample: MechanicsSample,
) -> Finding | None:
    """Why this attempt ended, when the log supports saying.

    The only `inferred` finding this area mints, because it is the only
    judgement. The four facts behind it -- three measured, one derived --
    are stated in the finding rather than summarised, so a reader who
    disagrees can see what it read.

    It withholds rather than guesses. A wipe where the raid mostly stood and
    the boss was nearly dead is neither an execution failure nor a wall, and
    the honest answer is to say nothing -- the same habit the comparison axes
    keep when their samples are too thin.

    Boss health is `boss_percentage`, never `fight_percentage`. The two are
    different quantities and diverged 51.12 against 3.76 on one measured
    attempt.
    """
    if encounter.kill or not sample.members or encounter.boss_percentage is None:
        return None

    size = encounter.size or len(encounter.players)
    if size <= 0:
        return None

    died = len({death.actor_id for death in deaths})
    alive = max(size - died, 0)
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
            "left. The deaths came first: a raid this far down cannot make the damage."
        )
    elif dismantled:
        headline = "execution: the raid was taken apart"
        story = (
            f"{died} of {size} died, against a median of {reference_deaths:.0f} across "
            "the reference kills. This attempt ended before the damage question could "
            "be asked."
        )
    elif stalled and alive / size >= INTACT_SHARE:
        headline = "throughput: the raid held and the damage was not enough"
        story = (
            f"{alive} of {size} were still alive, and the boss finished on "
            f"{encounter.boss_percentage:.1f}% health after "
            f"{encounter.duration_seconds:.0f}s against the reference kills' "
            f"{reference_seconds:.0f}s. Nobody died and it still was not enough."
        )
    else:
        return None

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
            f"{died} deaths against a reference median of {reference_deaths:.0f}",
        ),
        facts=(
            FindingFact(label="Alive at the end", value=f"{alive} of {size}"),
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

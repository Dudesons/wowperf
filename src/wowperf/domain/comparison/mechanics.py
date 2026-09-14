# ABOUTME: The per-ability landing profile of one fight, and how two of them compare.
# ABOUTME: Landings only -- the table's damage is mitigated and cannot meet the event stream's.

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, SAMPLE_SIZE, too_few
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantifier_for


class AbilityTakenRow(Frozen):
    """One ability's damage-taken row, as `viewBy: Ability` reports it.

    Damage is deliberately absent. The table's `total` is mitigated -- it
    equals the event stream's health damage plus absorbs -- and the
    unmitigated figure `players.damage.*` ranks on is not exposed and not
    reconstructible. Carrying both would put two figures for one ability on
    one page, measured up to 4.61x apart on a real fight, with nothing a
    reader could reconcile them by.
    """

    ability_id: int
    ability_name: str
    hit_count: int = 0
    tick_count: int = 0
    miss_count: int = 0
    tick_miss_count: int = 0
    # Each source's `type`, verbatim: "Boss", "NPC" or "Pet" for a hostile
    # source, a class name for a player. Empty on a row whose sources array
    # was empty, which was observed carrying a miss count and no damage.
    source_types: tuple[str, ...] = ()

    @property
    def landings(self) -> int:
        """How many times this ability actually landed.

        No single field counts this. Measured 2026-09-14: hits, ticks, misses
        and tick misses summed over one fight's 26 rows equalled the event
        count exactly, so hits plus ticks is what landed and the two miss
        counts are what did not.
        """
        return self.hit_count + self.tick_count


class ReferenceKillRow(Frozen):
    """One kill from the `execution` leaderboard, as a reference candidate.

    Carries no keystone level, no bracket and no affixes: a boss fight has
    none of them, and a row that cannot express a keystone level cannot be
    handed to a Mythic+ comparison by accident.
    """

    report_code: str
    fight_id: int
    difficulty: int
    size: int
    duration_ms: int
    deaths: int = 0

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000


def select_reference_kills(
    rows: tuple[ReferenceKillRow, ...],
    *,
    our_size: int,
    our_difficulty: int,
    limit: int = SAMPLE_SIZE,
) -> tuple[ReferenceKillRow, ...]:
    """References comparable to our own fight, in leaderboard order.

    Both filters refuse rather than annotate. Difficulty because the master
    design already refuses a cross-difficulty comparison outright. Size because
    this comparison is a landing rate over a whole raid: measured 2026-09-14, a
    single page spanned 14 to 30 against our 20, and a 30-player reference
    reports half again as many landings for headcount alone. A page holds
    fifty rows, so matching exactly usually leaves plenty.
    """
    matching = [
        row for row in rows if row.size == our_size and row.difficulty == our_difficulty
    ]
    return tuple(matching[:limit])


class MechanicsMember(Frozen):
    """One reference kill's ability-taken rows, alongside the row that dates and sizes it."""

    row: ReferenceKillRow
    abilities: tuple[AbilityTakenRow, ...]


class MechanicsSample(Frozen):
    """The reference kills a mechanics comparison may draw on."""

    members: tuple[MechanicsMember, ...] = ()


PLAYER_SOURCE_TYPES = frozenset(
    {
        "DeathKnight", "DemonHunter", "Druid", "Evoker", "Hunter", "Mage", "Monk",
        "Paladin", "Priest", "Rogue", "Shaman", "Warlock", "Warrior",
    }
)
"""Source types that mean a player dealt the damage, not the encounter.

Measured 2026-09-14: a damage-taken row's `sources[].type` reads "Boss", "NPC"
or "Pet" for a hostile source and the class name for a player, and every row
observed had homogeneous sources. Held as the *player* set rather than the
hostile one so the filter fails toward showing a mechanic: an unrecognised
type is kept, because an ability wrongly shown is visible and an ability
wrongly hidden is not.
"""

MECHANIC_MULTIPLE = 2.0
"""Taking this many times the sample's median rate of one ability is worth saying.

The same threshold `players.damage.*` uses against a group median, for the same
reason: below it, sample noise and a real difference are indistinguishable.
"""

MAX_MECHANICS_REPORTED = 5
"""At most this many abilities, worst gap first, matching `MAX_OUTLIERS_REPORTED`."""


def hostile_rows(rows: tuple[AbilityTakenRow, ...]) -> tuple[AbilityTakenRow, ...]:
    """Rows the encounter dealt, dropping those a friendly player dealt."""
    return tuple(
        row
        for row in rows
        if not (row.source_types and all(kind in PLAYER_SOURCE_TYPES for kind in row.source_types))
    )


def _rate(landings: int, seconds: float) -> float:
    return landings / seconds * 60


def compare_mechanics(
    ours: tuple[AbilityTakenRow, ...],
    our_seconds: float,
    sample: MechanicsSample,
    *,
    scope: str,
) -> list[Finding]:
    """Abilities this raid took far more often than kills of the same boss did.

    States landings per minute and nothing else. It never says a mechanic was
    missed: that is a claim about intent no table supports, and master design
    5.5 refuses it. The reader is handed two counts and draws their own
    conclusion.
    """
    # An empty sample means no comparison ran at all, which the caller states
    # once. Repeating it per ability would bury the findings that did run.
    if not sample.members or our_seconds <= 0:
        return []

    their_rows = [
        {row.ability_id: row for row in hostile_rows(member.abilities)}
        for member in sample.members
    ]
    total = len(sample.members)

    candidates: list[tuple[float, Finding]] = []
    for our_row in hostile_rows(ours):
        our_rate = _rate(our_row.landings, our_seconds)
        if our_rate <= 0:
            continue

        # A member that never took this ability contributes a zero, not an
        # absence. The encounter is fixed, so both sides draw from the same
        # ability set, and an ability we took and they did not is precisely
        # the finding. Dropping them would also let the denominator drift
        # from the number of references the title names.
        their_rates = [
            _rate(rows[our_row.ability_id].landings, member.row.duration_seconds)
            if our_row.ability_id in rows
            else 0.0
            for rows, member in zip(their_rows, sample.members, strict=True)
        ]
        carrying = sum(1 for rows in their_rows if our_row.ability_id in rows)

        their_median = median(their_rates)
        low, high = observed_range(their_rates)
        # A ratio against zero is not computed. Where the sample took none and
        # we took some, the gap is the whole finding and the evidence says so.
        if their_median > 0 and our_rate / their_median < MECHANIC_MULTIPLE:
            continue

        candidates.append(
            (
                our_rate - their_median,
                Finding(
                    id="mechanics.ability",
                    title=(
                        f"{scope} took {our_row.landings} of {our_row.ability_name} "
                        f"where the references took a median of {their_median:.1f} a minute"
                    ),
                    detail=(
                        f"{our_rate:.1f} landings a minute against a reference median of "
                        f"{their_median:.1f}. This states a difference, not a mistake: "
                        "whether any single landing was avoidable is not something the "
                        "log records."
                    ),
                    confidence=Confidence.MEASURED,
                    seconds_lost=None,
                    evidence=(
                        f"ours {our_rate:.1f} a minute over {our_seconds:.0f}s",
                        f"reference median {their_median:.1f} a minute",
                        f"range {low:.1f} to {high:.1f} across {total} reference kills",
                        f"{count_phrase(carrying, total)} references took it at all",
                    ),
                    facts=(
                        FindingFact(
                            label="This raid",
                            value=f"{our_rate:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        FindingFact(
                            label="Reference median",
                            value=f"{their_median:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        FindingFact(label="Range", value=f"{low:.1f} to {high:.1f}"),
                        FindingFact(label="Landings", value=f"{our_row.landings}"),
                    ),
                    ability_id=our_row.ability_id,
                    ability_name=our_row.ability_name,
                    quantifier=quantifier_for(carrying, total),
                ),
            )
        )

    candidates.sort(key=lambda pair: -pair[0])
    findings = [
        finding.model_copy(update={"id": f"mechanics.ability.{rank}"})
        for rank, (_, finding) in enumerate(candidates[:MAX_MECHANICS_REPORTED])
    ]
    # Reuses the sample module's own wording rather than inventing a second way
    # to say the same thing.
    if total < MIN_SAMPLE_FOR_AGGREGATE:
        return too_few(findings, total)
    return findings

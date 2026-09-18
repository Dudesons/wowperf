# ABOUTME: The per-ability landing profile of one fight, and how two of them compare.
# ABOUTME: Landings only -- the table's damage is mitigated and cannot meet the event stream's.
# ABOUTME: Also holds compare_lethal_abilities: a death count, read straight off the event stream.

from collections import Counter
from collections.abc import Mapping, Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.sample import MIN_SAMPLE_FOR_AGGREGATE, SAMPLE_SIZE, too_few
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.events import Death
from wowperf.domain.findings import (
    Confidence,
    Finding,
    FindingFact,
    quantifier_for,
    quantity,
)
from wowperf.domain.phase_windows import PhaseShare


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
    limit: int | None = SAMPLE_SIZE,
) -> tuple[ReferenceKillRow, ...]:
    """References comparable to our own fight, in leaderboard order.

    Size alone: this comparison is a landing rate over a whole raid, measured
    2026-09-14, a single page spanned 14 to 30 against our 20, and a 30-player
    reference reports half again as many landings for headcount alone. A page
    holds fifty rows, so matching exactly usually leaves plenty.

    `limit` of `None` returns every match rather than the first few. A caller
    that discards rows *after* this filter has to ask for all of them and stop
    at its own count, or each discard shrinks the sample below what the
    leaderboard actually offered.

    There is no difficulty filter here, on purpose: `reference_kills` already
    passes our own difficulty as the query's own argument, so the API never
    returns a row at another one, and a row carries no `difficulty` field to
    re-check against in any case (see `.claude/skills/wcl-api/SKILL.md`,
    "`fightRankings` echoes no `difficulty` per row", dated 2026-09-14). An
    earlier version of this function filtered on `row.difficulty ==
    our_difficulty`, a comparison the fixture that tested it could satisfy but
    the live API never sent a row to fail -- removed rather than kept as a
    filter that can never fire in production.
    """
    matching = [row for row in rows if row.size == our_size]
    return tuple(matching if limit is None else matching[:limit])


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


def _landings_by_ability(member: MechanicsMember) -> dict[int, AbilityTakenRow]:
    """One reference kill's hostile rows, addressable by ability id."""
    return {row.ability_id: row for row in hostile_rows(member.abilities)}


def _worth_reporting(our_rate: float, their_rate: float) -> bool:
    """Whether the gap between two landing rates clears the bar for a finding.

    A ratio against zero is not computed. Where the reference side took none
    and we took some, the gap is the whole finding and the evidence says so.
    """
    return their_rate <= 0 or our_rate / their_rate >= MECHANIC_MULTIPLE


def _ranked(candidates: list[tuple[float, Finding]]) -> list[Finding]:
    """The widest gaps first, capped, each numbered by where it landed.

    The rank is assigned after the sort and the cap, so a finding's id says
    where it sits on the page rather than where it was built.
    """
    candidates.sort(key=lambda pair: -pair[0])
    return [
        finding.model_copy(update={"id": f"mechanics.ability.{rank}"})
        for rank, (_, finding) in enumerate(candidates[:MAX_MECHANICS_REPORTED])
    ]


def _phase_fact(
    shares: Mapping[int, PhaseShare] | None, ability_id: int
) -> tuple[tuple[FindingFact, ...], tuple[str, ...]]:
    """One ability's phase label, as a fact and an evidence line, or nothing.

    Deliberately returns no reference figure of any kind. A reference kill's
    ability table carries no timestamps, so there is no reference phase to
    compare against and a fact implying one would be unfalsifiable -- design
    section 9.
    """
    share = (shares or {}).get(ability_id)
    if share is None:
        return (), ()
    return (
        (
            FindingFact(
                label="Mostly in",
                value=share.phase.name,
                confidence=Confidence.DERIVED,
            ),
        ),
        (f"{share.landings} of {share.total} landings fell in {share.phase.name}",),
    )


def compare_mechanics(
    ours: tuple[AbilityTakenRow, ...],
    our_seconds: float,
    sample: MechanicsSample,
    *,
    scope: str,
    phase_shares: Mapping[int, PhaseShare] | None = None,
) -> list[Finding]:
    """Abilities this raid took far more often than kills of the same boss did.

    States landings per minute on both sides and nothing else. It never says a
    mechanic was missed: that is a claim about intent no table supports, and
    master design 5.5 refuses it. The reader is handed two rates and draws
    their own conclusion.

    Below `MIN_SAMPLE_FOR_AGGREGATE` comparable references the comparison is
    made against a single reference kill, exactly as the route and tempo axes
    do below the same floor. A median of two is a mean of two, and `too_few`'s
    note -- "a single reference, not an aggregate" -- is only true of a finding
    that states one.
    """
    # An empty sample means no comparison ran at all, which the caller states
    # once. Repeating it per ability would bury the findings that did run.
    if not sample.members or our_seconds <= 0:
        return []

    # A member with a zero or negative duration has nothing to divide by, and
    # nothing upstream refuses it: `select_reference_kills` matches size
    # only. Dropped before anything is counted, so the denominator, every
    # "N of M" phrase in the evidence and the floor below all see the same set
    # of members that the rates themselves were drawn from.
    members = tuple(member for member in sample.members if member.row.duration_seconds > 0)
    if not members:
        return []

    if len(members) < MIN_SAMPLE_FOR_AGGREGATE:
        # Reuses the sample module's own wording rather than inventing a second
        # way to say the same thing.
        return too_few(
            _against_one(ours, our_seconds, members[0], scope, phase_shares), len(members)
        )
    return _against_sample(ours, our_seconds, members, scope, phase_shares)


def _against_one(
    ours: tuple[AbilityTakenRow, ...],
    our_seconds: float,
    member: MechanicsMember,
    scope: str,
    phase_shares: Mapping[int, PhaseShare] | None = None,
) -> list[Finding]:
    """Our landing rates against one reference kill's own, that kill named.

    The below-floor fallback `compare_mechanics` delegates to, and the sibling
    of `compare_route` and `compare_tempo`'s own pairwise forms. No median, no
    range and no count across a sample appear here, because there is one
    reference: stating any of them would describe a population this comparison
    never drew. Naming the reference is honest for the same reason it is in
    `compare_route`'s pairwise rows -- this is one kill's comparison, not a
    claim about a sample that happens to rest on one kill.
    """
    theirs = _landings_by_ability(member)
    their_seconds = member.row.duration_seconds

    candidates: list[tuple[float, Finding]] = []
    for our_row in hostile_rows(ours):
        our_rate = _rate(our_row.landings, our_seconds)
        if our_rate <= 0:
            continue

        # A reference that never took this ability took it at a rate of zero,
        # not at no rate at all: the encounter is fixed, so both sides draw
        # from the same ability set, and an ability we took and it did not is
        # precisely the finding.
        their_row = theirs.get(our_row.ability_id)
        their_rate = _rate(their_row.landings, their_seconds) if their_row else 0.0
        if not _worth_reporting(our_rate, their_rate):
            continue

        phase_facts, phase_evidence = _phase_fact(phase_shares, our_row.ability_id)
        candidates.append(
            (
                our_rate - their_rate,
                Finding(
                    id="mechanics.ability",
                    title=(
                        f"{scope} took {our_row.ability_name} {our_rate:.1f} times a minute "
                        f"where the reference took {their_rate:.1f} a minute"
                    ),
                    detail=(
                        f"{our_rate:.1f} landings a minute against one reference kill's "
                        f"{their_rate:.1f}. This states a difference, not a mistake: "
                        "whether any single landing could have been prevented is not "
                        "something the log records."
                    ),
                    confidence=Confidence.DERIVED,
                    seconds_lost=None,
                    evidence=(
                        f"ours {our_rate:.1f} a minute over {our_seconds:.0f}s",
                        f"the reference {their_rate:.1f} a minute over {their_seconds:.0f}s",
                        f"reference kill {member.row.report_code} fight {member.row.fight_id}",
                    )
                    + phase_evidence,
                    facts=(
                        FindingFact(
                            label="This raid",
                            value=f"{our_rate:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        FindingFact(
                            label="Reference",
                            value=f"{their_rate:.1f} a minute",
                            confidence=Confidence.DERIVED,
                        ),
                        # Named rather than left implicit, as
                        # `compare.spells.rate`'s own single-reference row does:
                        # this shape has no median and no range, and a panel
                        # printing either label would claim a sample nobody drew.
                        FindingFact(label="Sample", value="1 reference kill"),
                        FindingFact(label="Landings", value=f"{our_row.landings}"),
                    )
                    + phase_facts,
                    ability_id=our_row.ability_id,
                    ability_name=our_row.ability_name,
                ),
            )
        )

    return _ranked(candidates)


def _against_sample(
    ours: tuple[AbilityTakenRow, ...],
    our_seconds: float,
    members: Sequence[MechanicsMember],
    scope: str,
    phase_shares: Mapping[int, PhaseShare] | None = None,
) -> list[Finding]:
    """Our landing rates against the median of the sample's own, with its spread."""
    their_rows = [_landings_by_ability(member) for member in members]
    total = len(members)

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
            for rows, member in zip(their_rows, members, strict=True)
        ]
        carrying = sum(1 for rows in their_rows if our_row.ability_id in rows)

        their_median = median(their_rates)
        low, high = observed_range(their_rates)
        if not _worth_reporting(our_rate, their_median):
            continue

        phase_facts, phase_evidence = _phase_fact(phase_shares, our_row.ability_id)
        candidates.append(
            (
                our_rate - their_median,
                Finding(
                    id="mechanics.ability",
                    title=(
                        f"{scope} took {our_row.ability_name} {our_rate:.1f} times a minute "
                        f"where the references took a median of {their_median:.1f} a minute"
                    ),
                    detail=(
                        f"{our_rate:.1f} landings a minute against a reference median of "
                        f"{their_median:.1f}. This states a difference, not a mistake: "
                        "whether any single landing could have been prevented is not "
                        "something the log records."
                    ),
                    confidence=Confidence.DERIVED,
                    seconds_lost=None,
                    evidence=(
                        f"ours {our_rate:.1f} a minute over {our_seconds:.0f}s",
                        f"reference median {their_median:.1f} a minute",
                        f"range {low:.1f} to {high:.1f} across "
                        f"{quantity(total, 'reference kill', 'reference kills')}",
                        f"{count_phrase(carrying, total)} references took it at all",
                    )
                    + phase_evidence,
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
                    )
                    + phase_facts,
                    ability_id=our_row.ability_id,
                    ability_name=our_row.ability_name,
                    quantifier=quantifier_for(carrying, total),
                ),
            )
        )

    return _ranked(candidates)


def _reference_deaths(
    members: tuple[MechanicsMember, ...],
) -> tuple[str, str, str, Confidence | None]:
    """What the reference kills lost, as a title phrase, a fact, an evidence line and its badge.

    Below `MIN_SAMPLE_FOR_AGGREGATE` members this names a single reference kill
    rather than a median, exactly as `compare_mechanics` does one function
    above: a median of two is a mean of two, and the sample label must not
    claim an aggregate nobody drew.

    The confidence returned alongside the phrase is not the same in both
    branches. A median is a figure this function computed from the sample, so
    it is `derived`, the same badge `_phase_fact` gives its own computed
    figure. A single reference kill's death count is read straight off its
    row with no computation in between, so it is measured -- `None`, per
    `FindingFact`'s own rule that an unset confidence means exactly that.
    """
    counts = [float(member.row.deaths) for member in members]
    if len(counts) >= MIN_SAMPLE_FOR_AGGREGATE:
        low, high = observed_range(counts)
        middle = median(counts)
        return (
            f"a median of {middle:.0f}",
            f"{len(counts)} reference kills",
            f"reference kills lost {low:.0f} to {high:.0f} players, median {middle:.0f}",
            Confidence.DERIVED,
        )
    return (
        f"{counts[0]:.0f}",
        "1 reference kill",
        f"one reference kill lost {counts[0]:.0f} players in total",
        None,
    )


def compare_lethal_abilities(
    deaths: tuple[Death, ...],
    sample: MechanicsSample,
) -> list[Finding]:
    """Abilities that killed our raid, against what the reference kills lost in total.

    This is the one comparison in this area that judges rather than describes.
    Master design 5.5 refuses to call a hit avoidable, because a damage-taken
    table cannot tell a careless player from one soaking on purpose. A death is
    different: nobody dies to a mechanic deliberately, so a death count needs no
    claim about intent to mean something.

    The two sides are deliberately not symmetrical, and the wording says so:
    ours is one ability's kills, theirs is everything that killed anyone. A
    per-ability reference death count would need each reference kill's own
    death stream, which is a query per candidate.
    """
    if not deaths or not sample.members:
        return []

    tally: Counter[tuple[int, str]] = Counter(
        (death.killing_blow_id, death.killing_blow) for death in deaths
    )
    phrase, sample_label, evidence_line, reference_confidence = _reference_deaths(sample.members)

    ranked = sorted(tally.items(), key=lambda pair: (-pair[1], pair[0][1]))
    findings = []
    for rank, ((ability_id, ability_name), killed) in enumerate(ranked[:MAX_MECHANICS_REPORTED]):
        findings.append(
            Finding(
                id=f"mechanics.lethal.{rank}",
                title=(
                    f"{ability_name} killed {quantity(killed, 'player', 'players')}, "
                    f"where the reference kills lost {phrase} to everything combined"
                ),
                detail=(
                    f"{killed} of this raid's deaths came from {ability_name}. The "
                    "reference figure counts every death in those kills, from any "
                    "source: it is an upper bound covering every source, not a "
                    "per-ability figure."
                ),
                confidence=Confidence.DERIVED,
                evidence=(f"{ability_name} killed {killed}", evidence_line),
                facts=(
                    FindingFact(label="Killed by this", value=f"{killed}"),
                    FindingFact(
                        label="Reference deaths, all sources",
                        value=phrase,
                        confidence=reference_confidence,
                    ),
                    FindingFact(label="Sample", value=sample_label),
                ),
                ability_id=ability_id,
                ability_name=ability_name,
            )
        )
    return findings

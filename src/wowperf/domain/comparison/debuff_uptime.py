# ABOUTME: Compares one player's debuff coverage over every enemy against their spec's parses.
# ABOUTME: Judged on Overall coverage by the buff family's thresholds; stretches and reach describe.

from collections.abc import Collection, Sequence

from wowperf.domain.comparison.boss_debuffs import BossDebuffs, Withheld, encounter_share
from wowperf.domain.comparison.key_debuffs import KeyDebuffs, StretchCover
from wowperf.domain.comparison.measures import (
    BossCell,
    DebuffReach,
    DebuffRow,
    DebuffTable,
    Verdict,
)
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, observed_range
from wowperf.domain.comparison.uptime import (
    MAX_AURAS_REPORTED,
    carried_fractions,
    carried_shares,
    measured_or,
    pairwise_gaps,
    stretch_cell,
    uptime_measures,
)
from wowperf.domain.comparison.wording import DUNGEON
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity

ID_PREFIX = "compare.uptime.debuff"

STRETCH = "enemy-alive time"

GAP_DETAIL = (
    "Both figures are the share of enemy-alive time, summed over every enemy of the key, that "
    "carried this debuff from the player or their pets: a trash mob from the first debuff anyone "
    "put on it to its death, an add of a boss fight the same way, a single boss over its whole "
    "pull, and a council's bosses each from the pull's start to their own death, or to the "
    "pull's end if they did not die there. That is comparable even though the keys ran for "
    "different lengths. A boss pull with no boss found counts every enemy in it as an add, on "
    f"both sides. {DUNGEON.uptime_hedge} The intervals are rebuilt from the log's own "
    "applications and removals rather than read from a table."
)


def coverage_fractions(
    cover: StretchCover, names: Sequence[tuple[int, str]]
) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of this stretch's alive time it covered)."""
    if cover.alive_ms <= 0:
        return {}
    covered = dict(cover.covered)
    return {
        ability_id: (name, covered.get(ability_id, 0) / cover.alive_ms)
        for ability_id, name in names
    }


def debuff_fractions(debuffs: KeyDebuffs) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of the key's summed enemy-alive time it covered): Overall."""
    return coverage_fractions(debuffs.overall, debuffs.names)


def per_member_fractions(
    members: Sequence[ParseMember],
) -> tuple[dict[int, str], list[dict[int, float]]]:
    """Each member's Overall shares above zero, and every name seen, for `uptime_measures`.

    A share of zero reads the same as never having applied the debuff at all,
    the reading the buff family gives a band that never meets its stretch.
    """
    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in members:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        per_member.append(carried_fractions(debuff_fractions(member.debuffs), names))
    return names, per_member


def _unavailable(our_name: str, detail: str, evidence: tuple[str, ...]) -> Finding:
    return Finding(
        id=f"{ID_PREFIX}.unavailable",
        title=f"Debuff coverage could not be compared for {our_name}",
        detail=(
            "A debuff comparison needs the enemy-debuff stream, and at least one enemy "
            f"measured, on our side and on a reference's. {detail} No figures are reported "
            "rather than figures from one side."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=evidence,
    )


def compare_debuffs_sample(
    our: KeyDebuffs | None, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Where the sample's debuffs covered markedly more of their enemies' time than ours did.

    The order of the checks follows `uptime.compare_uptime_sample`. An empty
    sample says nothing here: `compare.parse.unavailable` already says it once.
    """
    if not sample.members:
        return []

    eligible = sample.debuff_eligible
    if not eligible:
        return [
            _unavailable(
                our_name,
                "No reference in the sample returned any debuff data.",
                (f"{count_phrase(0, len(sample.members))} references returned debuff data",),
            )
        ]

    if our is None or our.overall.alive_ms <= 0:
        return [
            _unavailable(
                our_name,
                "Our own side has no figure: its stream could not be read, or no enemy of the "
                "key could be measured.",
                (
                    f"our debuff data {'absent' if our is None else 'present'}",
                    "our measured enemy-alive time "
                    f"{0.0 if our is None else our.overall.seconds:.0f}s",
                ),
            )
        ]

    our_seconds = our.overall.seconds
    our_fractions = debuff_fractions(our)
    # A shared debuff is one slot a teammate's application took over, so our
    # share of it is no coverage of ours: it is neither a gap nor an unjudged zero.
    shared = dict(our.shared_with)
    if not sample.can_aggregate(eligible):
        return too_few(
            _pairwise(our_fractions, our_seconds, our_name, eligible[0], shared),
            len(eligible),
        )

    names, per_member = per_member_fractions(eligible)
    measures = [
        m
        for m in uptime_measures(our_fractions, per_member, names)
        if m.ability_id not in shared
    ]
    total = len(sample.members)
    missing = total - len(eligible)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )

    findings: list[Finding] = []
    for rank, m in enumerate(gaps[:MAX_AURAS_REPORTED]):
        low, high = observed_range(m.their_fractions)
        findings.append(
            Finding(
                id=f"{ID_PREFIX}.{rank}",
                title=(
                    f"{m.name} covered a median {m.their_median:.0%} of {STRETCH} "
                    f"across {len(m.their_fractions)} top parses; {m.ours:.0%} for {our_name}"
                ),
                detail=GAP_DETAIL,
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our_seconds:.0f}s of measured {STRETCH}",
                    f"range {low:.0%} to {high:.0%} across {len(m.their_fractions)} top parses",
                    f"{count_phrase(missing, total)} references had no debuff data",
                ),
                facts=(
                    FindingFact(label="Ours", value=f"{m.ours:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Reference median",
                                value=f"{m.their_median:.0%} of {STRETCH}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Observed range", value=f"{low:.0%} to {high:.0%}",
                                confidence=Confidence.DERIVED),
                    FindingFact(label="Sample", value=f"{len(m.their_fractions)} top parses"),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )

    unjudged = sorted({m.name for m in measures if m.verdict is Verdict.UNJUDGED})
    if unjudged:
        findings.append(_unjudged(our_name, unjudged))
    return findings


def _pairwise(
    our_fractions: dict[int, tuple[str, float]],
    our_seconds: float,
    our_name: str,
    theirs: ParseMember,
    shared: Collection[int],
) -> list[Finding]:
    """One reference, named, by the buff family's pairwise rule.

    A zero on our side is passed over here as it is on the buff side: below the
    floor there is no sample to say the debuff is one this build applies. A
    debuff in `shared` is passed over too, as it is in the sample's rule.
    """
    assert theirs.debuffs is not None  # chosen from debuff_eligible
    their_seconds = theirs.debuffs.overall.seconds
    gaps = [
        gap
        for gap in pairwise_gaps(our_fractions, debuff_fractions(theirs.debuffs))
        if gap[1] not in shared
    ]

    return [
        Finding(
            id=f"{ID_PREFIX}.{rank}",
            title=(
                f"{name} covered {their_share:.0%} of {theirs.character_name}'s "
                f"{STRETCH}, {our_share:.0%} of {our_name}'s"
            ),
            detail=GAP_DETAIL,
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ability {ability_id}",
                f"ours over {our_seconds:.0f}s of measured {STRETCH}",
                f"theirs over {their_seconds:.0f}s of measured {STRETCH}",
            ),
            facts=(
                FindingFact(label="Ours", value=f"{our_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Reference", value=f"{their_share:.0%} of {STRETCH}",
                            confidence=Confidence.DERIVED),
                FindingFact(label="Sample", value=f"1 reference {DUNGEON.reference_noun}"),
            ),
            ability_id=ability_id,
            ability_name=name,
        )
        for rank, (_, ability_id, name, our_share, their_share) in enumerate(
            gaps[:MAX_AURAS_REPORTED]
        )
    ]


def _unjudged(our_name: str, names: Sequence[str]) -> Finding:
    """Debuffs the sample kept on its enemies that ours never carried.

    A debuff names who applied it, so unlike a buff's zero this one is the
    player's own. What the log cannot say is whether their build has the
    ability at all, which is why it is named rather than judged. A debuff two
    teammates took over from each other is shared and never listed here. One
    a single teammate held still is: one holder cannot show that copies never
    coexist, so whether that teammate's copy left ours no room is unknown too.
    """
    count = len(names)
    return Finding(
        id=f"{ID_PREFIX}.unjudged",
        title=(
            f"{quantity(count, 'debuff', 'debuffs')} the sample kept on enemies "
            f"{'is' if count == 1 else 'are'} absent for {our_name}"
        ),
        detail=(
            "Each of these covered enough of the sample's enemy-alive time to compare, and never "
            "sat on an enemy of ours. A debuff names who applied it, so this zero is the "
            "player's own; what the log cannot say is whether their build has the ability at "
            "all, or whether a teammate's copy of a debuff that sits once on a target left no "
            "room for theirs. Check the talents before reading it as a missed button."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(names),
            f"applied by at least {MIN_SAMPLE_FOR_AGGREGATE} top parses each",
            "absent from every enemy we measured",
        ),
    )


def debuff_table(our: KeyDebuffs | None, sample: ParseSample) -> DebuffTable:
    """The debuff tables: each qualifying debuff judged on Overall, described per stretch.

    Gated exactly as `tables._auras` gates the buff table: no table below the
    floor, where the comparison states one reference rather than a median.

    Where there is no table, our own seconds, tally and counts still ride along
    when our stream was read: a zero left there by default would read in the
    findings file as a measurement. Without our stream the tally is None.
    """
    if our is None:
        return DebuffTable()
    overall = our.overall
    counted = DebuffTable(
        seconds=overall.seconds,
        tally=our.bosses.tally,
        deathless=our.bosses.deathless,
        unmeasured_no_death=our.unmeasured_no_death,
        undebuffed_deaths=our.undebuffed_deaths,
    )
    eligible = sample.debuff_eligible
    if overall.alive_ms <= 0 or not eligible or not sample.can_aggregate(eligible):
        return counted

    names, per_member = per_member_fractions(eligible)
    theirs: list[KeyDebuffs] = []
    for member in eligible:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        theirs.append(member.debuffs)
    shared = dict(our.shared_with)
    bosses: dict[int, str] = {}
    for window in our.bosses.windows:
        bosses.setdefault(window.encounter_id, window.name)

    rows = tuple(
        DebuffRow(
            uptime=m,
            trash=stretch_cell(
                measured_or(our.trash.coverage(m.ability_id), Withheld.NO_TRASH),
                [one.trash.coverage(m.ability_id) for one in theirs],
            ),
            bosses=stretch_cell(
                measured_or(our.on_bosses.coverage(m.ability_id), Withheld.NO_BOSS),
                [one.on_bosses.coverage(m.ability_id) for one in theirs],
            ),
            cells=tuple(
                _cell(our.bosses, eligible, m.ability_id, encounter_id, name)
                for encounter_id, name in bosses.items()
            ),
            reach=_reach(our, theirs, m.ability_id),
            shared_with=shared.get(m.ability_id, ()),
        )
        for m in uptime_measures(debuff_fractions(our), per_member, names)
    )
    return counted.model_copy(update={"rows": rows, "bosses": tuple(bosses.values())})


def _reach(our: KeyDebuffs, theirs: Sequence[KeyDebuffs], ability_id: int) -> DebuffReach:
    """One debuff's reach over each stretch, ours against the sample's: described, never judged.

    The references' Overall reaches behind the median ride along, for the reach
    table's Range and Sample.
    """
    overall = our.overall.reach(ability_id)
    assert overall is not None  # the table's gate leaves alive time, so at least one life
    their_overall = [one.overall.reach(ability_id) for one in theirs]
    return DebuffReach(
        overall=stretch_cell(overall, their_overall),
        overall_fractions=carried_shares(their_overall),
        trash=stretch_cell(
            measured_or(our.trash.reach(ability_id), Withheld.NO_TRASH),
            [one.trash.reach(ability_id) for one in theirs],
        ),
        bosses=stretch_cell(
            measured_or(our.on_bosses.reach(ability_id), Withheld.NO_BOSS),
            [one.on_bosses.reach(ability_id) for one in theirs],
        ),
    )


def _cell(
    our: BossDebuffs,
    members: Sequence[ParseMember],
    ability_id: int,
    encounter_id: int,
    name: str,
) -> BossCell:
    """One boss's cell. Descriptive only: the verdict is the row's, never a cell's.

    A member that never reached this boss, or whose pull of it was withheld,
    is not counted for it. Those that did and applied the debuff there give the
    median, at the same floor the row's own median keeps. That rule is
    `uptime.stretch_cell`'s, so this reads it rather than keeping a copy: a
    share that is not a figure is passed as None, and our own as its reason.
    """
    ours = encounter_share(our, ability_id, encounter_id)
    our_figure = ours if isinstance(ours, float) else (ours or Withheld.NO_BOSS)
    theirs: list[float | None] = []
    for member in members:
        assert member.debuffs is not None  # debuff_eligible guarantees it
        share = encounter_share(member.debuffs.bosses, ability_id, encounter_id)
        theirs.append(share if isinstance(share, float) else None)
    cell = stretch_cell(our_figure, theirs)
    return BossCell(
        encounter_id=encounter_id,
        boss=name,
        ours=cell.ours,
        their_median=cell.their_median,
        withheld=cell.withheld,
    )

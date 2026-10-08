# ABOUTME: Compares one player's debuff uptime on bosses against their specialisation's parses.
# ABOUTME: Shares of measured boss time, judged by the buff family's own thresholds and median.

from collections.abc import Sequence

from wowperf.domain.comparison.boss_debuffs import BossDebuffs, Withheld, encounter_share
from wowperf.domain.comparison.measures import (
    BossCell,
    BossDebuffRow,
    BossDebuffTable,
    Verdict,
)
from wowperf.domain.comparison.sample import (
    MIN_SAMPLE_FOR_AGGREGATE,
    ParseMember,
    ParseSample,
    too_few,
)
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.comparison.uptime import (
    MAX_AURAS_REPORTED,
    carried_fractions,
    fractions_of,
    pairwise_gaps,
    seconds_up_in,
    uptime_measures,
)
from wowperf.domain.comparison.wording import DUNGEON
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity

ID_PREFIX = "compare.uptime.boss"

STRETCH = "boss time"

GAP_DETAIL = (
    "Both figures are the share of single-boss pull time the boss carried this debuff from "
    "the player or their pets, which is comparable even though the fights ran for different "
    "lengths. A pull whose bosses are a council is left out on both sides. "
    f"{DUNGEON.uptime_hedge} The intervals are rebuilt from the log's own applications and "
    "removals rather than read from a table."
)


def debuff_fractions(debuffs: BossDebuffs) -> dict[int, tuple[str, float]]:
    """Ability id to (name, share of measured boss seconds the boss carried it)."""
    seconds = debuffs.seconds
    if seconds <= 0:
        return {}
    return fractions_of(debuffs.auras, seconds_up_in(debuffs.measured), seconds)


def per_member_fractions(
    members: Sequence[ParseMember],
) -> tuple[dict[int, str], list[dict[int, float]]]:
    """Each member's shares above zero, and every name seen, for `uptime_measures`.

    A share of zero reads the same as never having applied the debuff at all,
    the reading the buff family gives a band that never meets a boss pull.
    """
    names: dict[int, str] = {}
    per_member: list[dict[int, float]] = []
    for member in members:
        assert member.boss_debuffs is not None  # debuff_eligible guarantees it
        per_member.append(carried_fractions(debuff_fractions(member.boss_debuffs), names))
    return names, per_member


def _unavailable(our_name: str, detail: str, evidence: tuple[str, ...]) -> Finding:
    return Finding(
        id=f"{ID_PREFIX}.unavailable",
        title=f"Boss debuff uptime could not be compared for {our_name}",
        detail=(
            "A boss debuff comparison needs the enemy-debuff stream, and at least one pull "
            f"with a single boss, on our side and on a reference's. {detail} No figures are "
            "reported rather than figures from one side."
        ),
        confidence=Confidence.MEASURED,
        seconds_lost=None,
        evidence=evidence,
    )


def compare_boss_debuffs_sample(
    our: BossDebuffs | None, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Where the sample's bosses carried a debuff over markedly more of their time than ours did.

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

    if our is None or our.seconds <= 0:
        return [
            _unavailable(
                our_name,
                "Our own side has no figure: its stream could not be read, or none of its "
                "boss pulls held a single boss.",
                (
                    f"our debuff data {'absent' if our is None else 'present'}",
                    f"our measured boss time {0.0 if our is None else our.seconds:.0f}s",
                ),
            )
        ]

    our_fractions = debuff_fractions(our)
    if not sample.can_aggregate(eligible):
        return too_few(_pairwise(our_fractions, our.seconds, our_name, eligible[0]), len(eligible))

    names, per_member = per_member_fractions(eligible)
    measures = uptime_measures(our_fractions, per_member, names)
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
                    f"{m.name} was on the boss a median {m.their_median:.0%} of {STRETCH} "
                    f"across {len(m.their_fractions)} top parses; {m.ours:.0%} for {our_name}"
                ),
                detail=GAP_DETAIL,
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our.seconds:.0f}s of measured boss pulls",
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
) -> list[Finding]:
    """One reference, named, by the buff family's pairwise rule.

    A zero on our side is passed over here as it is on the buff side: below the
    floor there is no sample to say the debuff is one this build applies.
    """
    assert theirs.boss_debuffs is not None  # chosen from debuff_eligible
    their_seconds = theirs.boss_debuffs.seconds
    gaps = pairwise_gaps(our_fractions, debuff_fractions(theirs.boss_debuffs))

    return [
        Finding(
            id=f"{ID_PREFIX}.{rank}",
            title=(
                f"{name} was on the boss for {their_share:.0%} of {theirs.character_name}'s "
                f"{STRETCH}, {our_share:.0%} of {our_name}'s"
            ),
            detail=GAP_DETAIL,
            confidence=Confidence.DERIVED,
            seconds_lost=None,
            evidence=(
                f"ability {ability_id}",
                f"ours over {our_seconds:.0f}s of measured boss pulls",
                f"theirs over {their_seconds:.0f}s of measured boss pulls",
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
    """Debuffs the sample kept on its bosses that ours never carried.

    A debuff names who applied it, so unlike a buff's zero this one is the
    player's own. What the log cannot say is whether their build has the
    ability at all, which is why it is named rather than judged.
    """
    count = len(names)
    return Finding(
        id=f"{ID_PREFIX}.unjudged",
        title=(
            f"{quantity(count, 'debuff', 'debuffs')} the sample kept on bosses "
            f"{'is' if count == 1 else 'are'} absent for {our_name}"
        ),
        detail=(
            "Each of these was on the boss over enough of the sample's boss time to compare, "
            "and never on ours. A debuff names who applied it, so this zero is the player's "
            "own; what the log cannot say is whether their build has the ability at all. Check "
            "the talents before reading it as a missed button."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(names),
            f"applied by at least {MIN_SAMPLE_FOR_AGGREGATE} top parses each",
            "absent from our own measured boss pulls",
        ),
    )


def boss_debuff_table(our: BossDebuffs | None, sample: ParseSample) -> BossDebuffTable:
    """The debuff table: each qualifying debuff, judged overall, with a cell per boss.

    Gated exactly as `tables._auras` gates the buff table: no table below the
    floor, where the comparison states one reference rather than a median.
    """
    eligible = sample.debuff_eligible
    if our is None or our.seconds <= 0 or not eligible or not sample.can_aggregate(eligible):
        return BossDebuffTable()

    names, per_member = per_member_fractions(eligible)
    measures = uptime_measures(debuff_fractions(our), per_member, names)
    bosses: dict[int, str] = {}
    for window in our.windows:
        bosses.setdefault(window.encounter_id, window.name)

    rows = tuple(
        BossDebuffRow(
            uptime=m,
            cells=tuple(
                _cell(our, eligible, m.ability_id, encounter_id, name)
                for encounter_id, name in bosses.items()
            ),
        )
        for m in measures
    )
    return BossDebuffTable(
        rows=rows, seconds=our.seconds, bosses=tuple(bosses.values()), tally=our.tally
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
    median, at the same floor the row's own median keeps.
    """
    ours = encounter_share(our, ability_id, encounter_id)
    if not isinstance(ours, float):
        return BossCell(
            encounter_id=encounter_id, boss=name, withheld=ours or Withheld.NO_BOSS
        )

    shares = []
    for member in members:
        assert member.boss_debuffs is not None  # debuff_eligible guarantees it
        shares.append(encounter_share(member.boss_debuffs, ability_id, encounter_id))
    reached = [share for share in shares if isinstance(share, float)]
    if not reached:
        return BossCell(
            encounter_id=encounter_id, boss=name, ours=ours, withheld=Withheld.NOT_REACHED
        )
    carried = [share for share in reached if share > 0.0]
    if len(carried) < MIN_SAMPLE_FOR_AGGREGATE:
        return BossCell(
            encounter_id=encounter_id, boss=name, ours=ours, withheld=Withheld.TOO_FEW
        )
    return BossCell(
        encounter_id=encounter_id, boss=name, ours=ours, their_median=median(carried)
    )

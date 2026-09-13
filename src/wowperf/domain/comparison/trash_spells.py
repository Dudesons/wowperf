# ABOUTME: Compares one player's cast rates on the trash packs two routes shared.
# ABOUTME: Only aligned packs count, so a rate measures play rather than the route.

from collections.abc import Sequence

from wowperf.domain.base import Frozen
from wowperf.domain.comparison.alignment import align_pulls
from wowperf.domain.comparison.measures import AbilityRate, Stretch, Verdict
from wowperf.domain.comparison.sample import ParseSample
from wowperf.domain.comparison.spells import (
    MAX_SPELLS_REPORTED,
    MIN_CASTS_TO_COMPARE,
    MIN_MEMBERS_WITH_ABILITY,
    RATE_GAP_MULTIPLE,
    casts_in,
    their_actor_id,
    verdict_for,
)
from wowperf.domain.comparison.statistics import count_phrase, median, observed_range
from wowperf.domain.findings import Confidence, Finding, FindingFact, quantity
from wowperf.domain.model import LoadedRun, Player, Run

MIN_ALIGNED_TRASH_SECONDS = 60.0
"""Aligned trash seconds a side must reach before its rate is argued from.

Measured 2026-09-13 against the cached responses, over two distributions. The
first is 106 real trash packs across 19 keystone fights in five dungeons: the
median pack ran 80.9s, a quarter ran under 57.3s, ten ran under 20s and the
shortest ran 6.8s. The second is what two real routes through one dungeon
actually share — six cross-report pairs on Murder Row, whose weaker side ran
644.8s to 786.9s of aligned trash. Between those two lies a wide empty stretch,
and this floor sits in it: every complete route measured keeps every reference,
while three quarters of single packs clear it alone, so a route that lined up
with only one ordinary pack is still compared.

A minute is also the unit the rate is stated in. Below it a figure in casts per
minute is an extrapolation rather than a measurement, which is the failure the
floor exists to stop: two casts over twenty seconds is six a minute and means
nothing, and the rate rows have no other guard against a small denominator.
"""


class AlignedTrash(Frozen):
    """The trash packs two routes shared, and the seconds each side spent on them."""

    our_pulls: frozenset[int] = frozenset()
    their_pulls: frozenset[int] = frozenset()
    our_seconds: float = 0.0
    their_seconds: float = 0.0

    @property
    def pack_count(self) -> int:
        """Our packs that found a counterpart — the denominator a title states."""
        return len(self.our_pulls)


def aligned_trash(ours: Run, theirs: Run) -> AlignedTrash:
    """The packs both groups fought, as pull indices and seconds on each side.

    Indices are collected into sets before any duration is summed, and the
    reason differs on the two sides. `align_pulls` runs a sweep after its main
    pass that pairs each of their unclaimed trash pulls back to the best
    counterpart among ours, with nothing marked taken, so one chain-pulled
    stretch of ours can appear in several matches — summing per match would
    inflate our own denominator and depress our own rate. Their indices cannot
    repeat, because the main pass claims each one and the sweep visits only
    what it left; the set on that side is defensive, not load-bearing.
    """
    alignment = align_pulls(ours, theirs)
    packs = alignment.our_packs
    ours_by_index = {pull.index: pull for pull in ours.pulls}
    theirs_by_index = {pull.index: pull for pull in theirs.pulls}

    our_pulls = {match.ours_index for match in alignment.matched if match.ours_index in packs}
    their_pulls = {
        match.theirs_index for match in alignment.matched if match.ours_index in packs
    }
    return AlignedTrash(
        our_pulls=frozenset(our_pulls),
        their_pulls=frozenset(their_pulls),
        our_seconds=sum(ours_by_index[i].duration_seconds for i in our_pulls),
        their_seconds=sum(
            theirs_by_index[i].duration_seconds for i in their_pulls if i in theirs_by_index
        ),
    )


def is_comparable(aligned: AlignedTrash) -> bool:
    """Whether both sides spent long enough on shared packs to state a rate.

    Both, not either: a rate is a ratio of two denominators and a thin one on
    the reference's side skews it exactly as badly as a thin one on ours.
    """
    return (
        aligned.our_seconds >= MIN_ALIGNED_TRASH_SECONDS
        and aligned.their_seconds >= MIN_ALIGNED_TRASH_SECONDS
    )


def compare_trash_spells_sample(
    ours: LoadedRun, our_player: Player, our_name: str, sample: ParseSample
) -> list[Finding]:
    """Cast rates on the trash packs our route shared with the sample's.

    Boss pulls are `compare_spells_sample`'s subject and are excluded here, so
    the two families never price the same seconds twice. No member is named:
    the claim is about the sample as a population, exactly as on the boss rows.
    """
    if not sample.members:
        return []

    ours_aligned: list[AlignedTrash] = []
    per_member: list[tuple[float, dict[int, int]]] = []
    names: dict[int, str] = {}
    for member in sample.members:
        actor_id = their_actor_id(member, member.row.character_name)
        aligned = aligned_trash(ours.run, member.run)
        if actor_id is None or not is_comparable(aligned):
            per_member.append((0.0, {}))
            continue
        ours_aligned.append(aligned)
        their_casts = casts_in(member.casts, actor_id, aligned.their_pulls)
        for ability_id, (name, _count) in their_casts.items():
            names.setdefault(ability_id, name)
        per_member.append(
            (
                aligned.their_seconds,
                {
                    ability_id: count
                    for ability_id, (_name, count) in their_casts.items()
                    if count >= MIN_CASTS_TO_COMPARE
                },
            )
        )

    if not ours_aligned:
        return [_unavailable_row(our_name, len(sample.members))]

    # Our own denominator is the union of every pack that aligned with anybody:
    # a pack one reference skipped is still a pack we fought and were compared on.
    our_pulls = frozenset().union(*(aligned.our_pulls for aligned in ours_aligned))
    our_seconds = sum(
        pull.duration_seconds for pull in ours.run.pulls if pull.index in our_pulls
    )
    if our_seconds <= 0:
        return [_unavailable_row(our_name, len(sample.members))]
    ours_on_trash = casts_in(ours.casts, our_player.actor_id, our_pulls)
    return _rate_rows(our_name, ours_on_trash, our_seconds, len(our_pulls), per_member)


def _unavailable_row(our_name: str, total: int) -> Finding:
    """No reference shared enough trash with our route to state a rate."""
    return Finding(
        id="compare.spells.trash.unavailable",
        title=f"Trash cast rates could not be compared for {our_name}",
        detail=(
            "A trash comparison needs packs both routes fought, matched by the enemy types in "
            "them, and enough time on them to divide by. No reference in the sample reached "
            "that, so no trash rates are reported rather than rates from packs only one group "
            "fought. Boss-pull rates are unaffected and are reported above."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            f"{count_phrase(0, total)} references shared enough trash to compare",
            f"a side must reach {MIN_ALIGNED_TRASH_SECONDS:.0f}s of aligned trash",
        ),
    )


def trash_rate_measures(
    ours_on_trash: dict[int, tuple[str, int]],
    our_seconds: float,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> tuple[AbilityRate, ...]:
    """Every ability compared on the shared packs, with the verdict it earned.

    The trash twin of `rate_measures`, sharing its bar through `verdict_for`
    so the two stretches cannot drift apart on what counts as a gap.
    """
    measures: list[AbilityRate] = []
    for ability_id, (name, our_count) in ours_on_trash.items():
        rates = [
            qualifying[ability_id] / their_seconds * 60
            for their_seconds, qualifying in per_member
            if ability_id in qualifying and their_seconds > 0
        ]
        if len(rates) < MIN_MEMBERS_WITH_ABILITY:
            continue
        our_rate = our_count / our_seconds * 60
        if our_rate <= 0:
            continue
        their_median = median(rates)
        measures.append(
            AbilityRate(
                ability_id=ability_id,
                name=name,
                ours=our_rate,
                their_median=their_median,
                their_rates=tuple(rates),
                stretch=Stretch.TRASH,
                verdict=verdict_for(our_rate, their_median),
            )
        )
    return tuple(measures)


def _rate_rows(
    our_name: str,
    ours_on_trash: dict[int, tuple[str, int]],
    our_seconds: float,
    pack_count: int,
    per_member: Sequence[tuple[float, dict[int, int]]],
) -> list[Finding]:
    """Abilities both sides cast on shared packs, where the sample's median is higher."""
    measures = trash_rate_measures(ours_on_trash, our_seconds, per_member)
    gaps = sorted(
        (m for m in measures if m.verdict is Verdict.BELOW),
        key=lambda m: m.their_median - m.ours,
        reverse=True,
    )
    above = sorted(
        (m for m in measures if m.verdict is Verdict.ABOVE),
        key=lambda m: m.ours - m.their_median,
        reverse=True,
    )
    # Compared against enough of the sample to argue from, and no gap wide
    # enough to report. Collected rather than dropped: silence on the page
    # read the same as never having been compared at all.
    level = [m.name for m in measures if m.verdict is Verdict.LEVEL]

    findings = []
    for rank, m in enumerate(gaps[:MAX_SPELLS_REPORTED]):
        low, high = observed_range(m.their_rates)
        findings.append(
            Finding(
                id=f"compare.spells.trash.rate.{rank}",
                title=(
                    f"{len(m.their_rates)} top parses cast {m.name} a median "
                    f"{m.their_median:.1f} times a minute across "
                    f"{quantity(pack_count, 'aligned pack', 'aligned packs')}; "
                    f"{our_name} casts it {m.ours:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of time spent on trash packs both routes "
                    "fought, matched by the enemy types in them. Restricting to shared packs is "
                    "what separates a rate about play from a rate about the route - but an "
                    "aligned pair is a comparable pair, not an identical one, so pack size still "
                    "varies within it and pull order still moves a rate."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our_seconds:.0f}s of aligned trash",
                    f"range {low:.1f} to {high:.1f} casts a minute across "
                    f"{len(m.their_rates)} top parses",
                ),
                facts=(
                    FindingFact(
                        label="Ours",
                        value=f"{m.ours:.1f} casts a minute",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(
                        label="Reference median",
                        value=f"{m.their_median:.1f} casts a minute",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(
                        label="Observed range",
                        value=f"{low:.1f} to {high:.1f}",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(label="Aligned packs", value=str(pack_count)),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )
    for rank, m in enumerate(above[:MAX_SPELLS_REPORTED]):
        low, high = observed_range(m.their_rates)
        findings.append(
            Finding(
                id=f"compare.spells.trash.above.{rank}",
                title=(
                    f"{our_name} casts {m.name} {m.ours:.1f} times a minute across "
                    f"{quantity(pack_count, 'aligned pack', 'aligned packs')}; "
                    f"{len(m.their_rates)} top parses cast it a median {m.their_median:.1f}"
                ),
                detail=(
                    "Both rates are casts per minute of time spent on trash packs both routes "
                    "fought. This row states a difference and no verdict: casting something "
                    "more often than the sample is not a fault, and on a class whose resources "
                    "are shared it means those resources did not go somewhere else, which is "
                    "the thing worth checking. Across trash it is the weaker of the two "
                    "directions, because pull size and what the group held move a rate upward "
                    "without any difference in play."
                ),
                confidence=Confidence.DERIVED,
                seconds_lost=None,
                evidence=(
                    f"ability {m.ability_id}",
                    f"ours over {our_seconds:.0f}s of aligned trash",
                    f"range {low:.1f} to {high:.1f} casts a minute across "
                    f"{len(m.their_rates)} top parses",
                ),
                facts=(
                    FindingFact(
                        label="Ours",
                        value=f"{m.ours:.1f} casts a minute",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(
                        label="Reference median",
                        value=f"{m.their_median:.1f} casts a minute",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(
                        label="Observed range",
                        value=f"{low:.1f} to {high:.1f}",
                        confidence=Confidence.DERIVED,
                    ),
                    FindingFact(label="Aligned packs", value=str(pack_count)),
                ),
                ability_id=m.ability_id,
                ability_name=m.name,
            )
        )
    if level:
        findings.append(_level_row(our_name, level, pack_count))
    return findings


def _level_row(our_name: str, names: Sequence[str], pack_count: int) -> Finding:
    """Abilities compared on the shared packs that produced no gap row."""
    ordered = sorted(set(names))
    return Finding(
        id="compare.spells.trash.level",
        title=(
            f"{quantity(len(ordered), 'ability', 'abilities')} {our_name} cast across "
            f"{quantity(pack_count, 'aligned pack', 'aligned packs')} "
            f"{'was' if len(ordered) == 1 else 'were'} compared and showed no gap"
        ),
        detail=(
            "Enough of the sample cast each of these on packs both routes fought, and our own "
            "rate was inside the band the rate rows use, in either direction: the sample's "
            f"median has to be {RATE_GAP_MULTIPLE} times ours, or ours {RATE_GAP_MULTIPLE} "
            "times theirs, before a row is written. Read it as 'no gap wide enough to "
            "report', never as 'the same rate'."
        ),
        confidence=Confidence.DERIVED,
        seconds_lost=None,
        evidence=(
            ", ".join(ordered),
            f"compared against at least {MIN_MEMBERS_WITH_ABILITY} top parses each",
        ),
    )

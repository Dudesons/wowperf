# ABOUTME: What repeats across one character's runs: judgements made again and again, and
# ABOUTME: measures on one side of the top parses in every run. Counts, never sums.

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import NamedTuple

from wowperf.domain.character.model import CharacterRun
from wowperf.domain.comparison.measures import Verdict
from wowperf.domain.comparison.statistics import median
from wowperf.domain.findings import (
    Confidence,
    Finding,
    least_certain,
    quantifier_for,
    quantity,
)

REPEAT_MIN_RUNS = 3
"""The fewest runs a repeated judgement may rest on, however few runs loaded."""

REPEAT_RULE = (
    "Judged again and again: a judgement the per-run analysis made in at least half of the "
    f"runs that loaded, and in at least {REPEAT_MIN_RUNS}."
)

ANALYSIS_FAMILIES_NOT_COUNTED = (
    "Not counted across runs, so the page saying nothing of them is not a clean bill: deaths and "
    "what each cost, missed interrupts, defensives, healing consumables, throughput cooldowns, "
    "heavy moments of damage, and talents. Defensive, healing-consumable and throughput-cooldown "
    "findings do not name their player in a form the count can read, and the talent comparison "
    "is made under one id whatever its outcome. Each run's own report states them."
)
"""The complement of the allowlist below, as a reader would name it.

The combat-potion and consumable-buff comparisons are counted, so the
consumables left out are the healing ones alone; `trash.overage` is the one
analysis-side family counted.
"""

COUNTED_NOT_SUMMED = (
    "Findings across runs are counted, never summed: seconds lost in different dungeons, at "
    "different keys and on different routes are not one quantity. Each count says how many runs "
    "it rests on, and each run's own figures are its own."
)

CHARACTER_FINDINGS_ARE_RANKED_NOT_ADDITIVE = (
    "Directions come first, then repeated judgements, each ordered by how many runs support "
    "it, never by seconds; findings are counted across runs, never summed."
)
"""The character page's ranked-not-additive warning, a sibling of the other commands' own.

Each command states its own: the Mythic+, raid and progression warnings name
their own findings' nestings and order, none of which a cross-run finding has.
The order is design section 5.4's: the page draws every direction before any
repeat, so a direction resting on fewer runs can sit above a repeat resting on
more; within each, `consistent_directions` and `repeated_judgements` sort by the
runs a finding rests on first. `COUNTED_NOT_SUMMED` stays among the rules, for
why runs' seconds are not one quantity.
"""

SUBJECT_FAMILIES = frozenset({
    "compare.spells.rate",
    "compare.spells.above",
    "compare.spells.missing",
    "compare.spells.trash.rate",
    "compare.spells.trash.above",
    "compare.uptime.self",
    "compare.uptime.debuff",
    "compare.gear.tier",
    "compare.consumables.potion",
})
"""The subject's judgement families: each fires only when something stands out.

`compare.talents` is not one: it is minted under the one id whether the build
could not be compared, matched, or differed, so it fires for every compared
player and a count of it would say nothing.
"""

SUBJECT_FAMILY_PREFIXES = (
    "compare.gear.enchant.",
    "compare.stats.rating.",
    "compare.consumables.buff.",
)
"""Judgement families whose id names what they judge after the prefix: a slot, a stat, a
category. What follows the prefix is part of the family, never a rank: an enchant's slot is
an int, and reading it as a rank would fold every slot into one family."""

RUN_FAMILIES = frozenset({"compare.route.skipped", "trash.overage"})
"""The run's own judgement families, which belong to nobody."""

_TITLES = {
    "compare.spells.rate": "Top parses cast {ability} more often than you on bosses",
    "compare.spells.above": "You cast {ability} more often than top parses on bosses",
    "compare.spells.trash.rate": "Top parses cast {ability} more often than you on trash",
    "compare.spells.trash.above": "You cast {ability} more often than top parses on trash",
    "compare.spells.missing": "Top parses cast {ability}; you never did",
    # Presence, never agency, as `comparison/uptime.py` words the run's own
    # finding: the aura table says a buff was present, not who put it there.
    "compare.uptime.self": "{ability} was up less of the key for you than for top parses",
    "compare.uptime.debuff": "Top parses' {ability} covered more of the enemies' lives than yours",
    "compare.gear.tier": "You wore fewer tier pieces than top parses",
    "compare.consumables.potion": "You drank fewer combat potions than top parses",
    "compare.route.skipped": "The group pulled a pack fast runs skipped",
    "trash.overage": "The group killed more trash than the key required",
}

# The suffix is what the id carries, not what the run's own title says: a slot
# is its index, since slot names are data the domain does not read, and a
# consumable category is its slug words, since its article-bearing label is too.
_PREFIX_TITLES = {
    "compare.gear.enchant.": "Top parses enchanted a slot you left bare (slot {suffix})",
    "compare.stats.rating.": "Your {suffix} share of secondary rating differed from top parses'",
    "compare.consumables.buff.": "Top parses carried a consumable buff you did not: {suffix}",
}

REPEAT_DETAIL = (
    "Counted once for each run in which that run's own analysis made this judgement; a run "
    "that made it twice counts once. It is a count, not a sum: each run's figures are its own "
    "and are listed below."
)


def family_of(finding: Finding, subject_slug: str) -> str | None:
    """The finding's family when it is one this page counts, or None.

    The subject's slug and a trailing rank index are removed: `.emberkin-0` and
    `.emberkin-2` are one character in two runs, and `.0` and `.3` one family
    ranked differently. A prefix family is matched before any rank is removed,
    so `compare.gear.enchant.7` keeps its slot.
    """
    family = finding.id
    if subject_slug and finding.player_slug == subject_slug:
        suffix = f".{subject_slug}"
        if family.endswith(suffix):
            family = family[: -len(suffix)]
        if family.startswith(SUBJECT_FAMILY_PREFIXES):
            return family
        head, _, last = family.rpartition(".")
        if head and last.isdigit():
            family = head
        if family in SUBJECT_FAMILIES:
            return family
        return None
    if finding.player_slug == "":
        head, _, last = family.rpartition(".")
        if head and last.isdigit():
            family = head
        if family in RUN_FAMILIES:
            return family
    return None


class _Fired(NamedTuple):
    run: CharacterRun
    finding: Finding


def _title(family: str, ability: str) -> str:
    if family in _TITLES:
        return _TITLES[family].format(ability=ability)
    for prefix, template in _PREFIX_TITLES.items():
        if family.startswith(prefix):
            return template.format(suffix=family[len(prefix):].replace("-", " "))
    raise ValueError(f"no title for {family!r}")


def _repeat(family: str, ability_id: int | None, hits: list[_Fired], total: int) -> Finding:
    ability = hits[-1].finding.ability_name
    count = len(hits)
    return Finding(
        id=f"character.repeat.{family}" + (f".{ability_id}" if ability_id is not None else ""),
        title=f"{_title(family, ability)}, in {count} of {total} runs",
        detail=REPEAT_DETAIL,
        confidence=least_certain(hit.finding.confidence for hit in hits),
        evidence=tuple(
            f"{hit.run.dungeon} +{hit.run.keystone_level}: {hit.finding.title}" for hit in hits
        ),
        ability_id=ability_id,
        ability_name=ability,
        quantifier=quantifier_for(count, total),
    )


def repeated_judgements(runs: Sequence[CharacterRun]) -> list[Finding]:
    total = len(runs)
    fired: dict[tuple[str, int | None], list[_Fired]] = defaultdict(list)
    for run in runs:
        seen: set[tuple[str, int | None]] = set()
        for finding in run.findings:
            family = family_of(finding, run.subject_slug)
            if family is None:
                continue
            key = (family, finding.ability_id)
            if key in seen:
                continue
            seen.add(key)
            fired[key].append(_Fired(run, finding))
    needed = max(REPEAT_MIN_RUNS, math.ceil(total / 2))
    found = [
        _repeat(family, ability_id, hits, total)
        for (family, ability_id), hits in fired.items()
        if len(hits) >= needed
    ]
    return sorted(found, key=lambda finding: (-len(finding.evidence), finding.id))


MIN_DIRECTION_RUNS = 6
"""The fewest runs that must have judged a measure before its direction is stated."""

DIRECTION_RATE_FLOOR = 0.10
"""The smallest median relative gap a cast-rate direction may rest on."""

DIRECTION_SHARE_FLOOR = 0.05
"""The smallest median gap, as a fraction, an uptime, a coverage or a stat share may rest on."""

_FLOOR_TOLERANCE = 1e-9
"""How far under a floor a gap may read and still sit on it.

A gap is a float subtraction: 0.60 - 0.55 reads 0.04999..., and a gap exactly
on the floor must count as on it.
"""

DIRECTION_RULE = (
    f"Every run, the same side: a measure judged in at least {MIN_DIRECTION_RUNS} runs, every "
    "one of them on the same side of the top parses' median, with a median gap of at least "
    f"{DIRECTION_RATE_FLOOR:.0%} for a cast rate or {DIRECTION_SHARE_FLOOR * 100:.0f} points for "
    "an uptime, a coverage or a stat share. A run counts only where its own comparison judged "
    "the row. These floors are chosen numbers, not measured ones, set well under the single-run "
    "thresholds on purpose: this reading exists to catch gaps no single run could call."
)

DIRECTIONS_WITHHELD_ID = "character.direction.withheld"

DIRECTION_DETAIL = (
    "Counted in each run whose own comparison judged this row; every one of them sat on the same "
    "side of that run's top parses. It states a difference, not a mistake, and a different build "
    "or a different job in the group can account for it."
)

_JUDGED = frozenset({Verdict.BELOW, Verdict.ABOVE, Verdict.LEVEL})
_RATE_KINDS = frozenset({"boss", "trash"})


class _Reading(NamedTuple):
    run: CharacterRun
    ours: float
    theirs: float


_Readings = dict[tuple[str, str], tuple[str, int | None, list[_Reading]]]
"""(kind, what it measures) -> (the name to print, the ability id or None, every judged reading)."""


def _readings(runs: Sequence[CharacterRun]) -> _Readings:
    """Every judged row of every run, keyed by kind and what it measures.

    A debuff row whose `shared_with` names anyone is left out whatever its
    verdict says, as the row's own docstring rules. The name printed is the
    first run's spelling of it.
    """
    found: _Readings = {}

    def add(kind: str, key: str, name: str, ability_id: int | None, run: CharacterRun,
            ours: float, theirs: float) -> None:
        _, _, readings = found.setdefault((kind, key), (name, ability_id, []))
        readings.append(_Reading(run, ours, theirs))

    for run in runs:
        measures = run.measures
        if measures is None:
            continue
        for kind, rates in (("boss", measures.boss), ("trash", measures.trash)):
            for rate in rates:
                if rate.verdict in _JUDGED:
                    add(kind, str(rate.ability_id), rate.name, rate.ability_id, run,
                        rate.ours, rate.their_median)
        for row in measures.auras:
            if row.uptime.verdict in _JUDGED:
                add("buff", str(row.uptime.ability_id), row.uptime.name, row.uptime.ability_id,
                    run, row.uptime.ours, row.uptime.their_median)
        for debuff in measures.debuffs.rows:
            if debuff.uptime.verdict in _JUDGED and not debuff.shared_with:
                add("debuff", str(debuff.uptime.ability_id), debuff.uptime.name,
                    debuff.uptime.ability_id, run, debuff.uptime.ours,
                    debuff.uptime.their_median)
        for stat in measures.stats:
            if stat.verdict in _JUDGED:
                add("stat", stat.name, stat.name, None, run, stat.ours, stat.their_median)
    return found


def _title_for(kind: str, name: str, below: bool, count: int) -> str:
    tail = f", in every one of {count} runs"
    if kind in _RATE_KINDS:
        where = "on bosses" if kind == "boss" else "on trash"
        return f"You cast {name} {'less' if below else 'more'} often than top parses {where}{tail}"
    if kind == "buff":
        return (f"{name} was up {'less' if below else 'more'} of the key for you than for top "
                f"parses{tail}")
    if kind == "debuff":
        return (f"Your {name} covered {'less' if below else 'more'} of the enemies' lives than "
                f"top parses'{tail}")
    return (f"Your {name} share of secondary rating sat {'below' if below else 'above'} top "
            f"parses'{tail}")


def _direction(kind: str, key: str, name: str, ability_id: int | None,
               readings: list[_Reading]) -> tuple[Finding, float] | None:
    """The measure's direction and its median gap, or None when the runs do not agree.

    An exact tie sits on neither side, so one tie breaks the unanimity as one
    dissent does.
    """
    below = all(one.ours < one.theirs for one in readings)
    above = all(one.ours > one.theirs for one in readings)
    if not (below or above):
        return None
    if kind in _RATE_KINDS:
        gaps = [abs(one.ours - one.theirs) / one.theirs if one.theirs > 0 else math.inf
                for one in readings]
        gap = median(gaps)
        if gap < DIRECTION_RATE_FLOOR - _FLOOR_TOLERANCE:
            return None
        lines = [f"{one.run.dungeon} +{one.run.keystone_level}: {one.ours:.1f} against "
                 f"{one.theirs:.1f} a minute" for one in readings]
        lines.append(f"median gap {gap:.0%}")
    else:
        gap = median([abs(one.ours - one.theirs) for one in readings])
        if gap < DIRECTION_SHARE_FLOOR - _FLOOR_TOLERANCE:
            return None
        lines = [f"{one.run.dungeon} +{one.run.keystone_level}: {one.ours:.0%} against "
                 f"{one.theirs:.0%}" for one in readings]
        lines.append(f"median gap {gap * 100:.0f} points")
    finding = Finding(
        id=f"character.direction.{kind}.{key}",
        title=_title_for(kind, name, below, len(readings)),
        detail=DIRECTION_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(lines),
        ability_id=ability_id,
        ability_name=name if ability_id is not None else "",
        quantifier="every",
    )
    return finding, gap


def consistent_directions(runs: Sequence[CharacterRun]) -> list[Finding]:
    """The measures every judging run placed on one side of the top parses' median.

    Fewer than `MIN_DIRECTION_RUNS` loaded runs withholds the whole source with
    a measured finding rather than lowering the bar. Ordered by how many runs
    support each direction, then by its median gap.
    """
    if len(runs) < MIN_DIRECTION_RUNS:
        return [
            Finding(
                id=DIRECTIONS_WITHHELD_ID,
                title=(f"Consistent directions are not stated: "
                       f"{quantity(len(runs), 'run', 'runs')} loaded, "
                       f"{MIN_DIRECTION_RUNS} are needed"),
                detail=(
                    "Below this many runs, a measure lands on one side of the top parses in every "
                    "run by chance alone too often for the count to mean anything, so the bar is "
                    "kept and the reading withheld."
                ),
                confidence=Confidence.MEASURED,
            )
        ]
    found: list[tuple[Finding, float]] = []
    for (kind, key), (name, ability_id, readings) in _readings(runs).items():
        if len(readings) < MIN_DIRECTION_RUNS:
            continue
        direction = _direction(kind, key, name, ability_id, readings)
        if direction is not None:
            found.append(direction)
    found.sort(key=lambda pair: (-len(pair[0].evidence), -pair[1], pair[0].id))
    return [finding for finding, _ in found]

# ABOUTME: One boss's answers across its pulls: how fast it died, why wipes ended, what over-landed.
# ABOUTME: Each rollup counts findings the pulls already carry; none reads the log a second time.

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence

from wowperf.domain.analysis.attempt_shape import verdict_kind, verdict_words
from wowperf.domain.analysis.progression_repeats import MAX_REPEAT_ABILITIES, capped_line
from wowperf.domain.comparison.kill_time import KILL_TIME_ID
from wowperf.domain.comparison.pace import PACE_ID
from wowperf.domain.encounter import Encounter
from wowperf.domain.findings import (
    Confidence,
    Finding,
    fight_ranges,
    quantifier_for,
    quantity,
)

KILL_SPEED_ID = "progression.lead.kill_speed"
VERDICTS_ID = "progression.lead.verdicts"
NEVER_TAKEN_ID = "progression.lead.never_taken"
OVERLANDING_ID = "progression.lead.overlanding"

MECHANICS_ABILITY_PREFIX = "mechanics.ability."

NO_REFERENCE_TOOK_IT = "none"
"""A per-pull `mechanics.ability.*` quantifier when no reference kill took the ability at all.

`compare_mechanics` sets that finding's quantifier to `quantifier_for(carrying,
total)` over the references that took the ability, so this is the one value
meaning none of them did. A single-reference reading carries no count of
references, so it never reads this.
"""

PULL_NOT_LOADED = "its pull did not load"
"""The reason a wipe whose pull was never drawn is counted under, read after "withheld, ".

The night's Provenance names each pull that failed and the failure itself, so
this says only that the pull did not load rather than repeating a transport
error in a summary line.
"""

KILL_SPEED_DETAIL = (
    "Read off the kill's own findings: its duration against the reference kills of this raid "
    "size and, where it was compared, its damage pace against theirs. The references are "
    "among the best kills of this boss, so a slower kill is the expected result; what this "
    "offers is where the gap opened, not that it exists."
)

VERDICTS_DETAIL = (
    "Each wipe's own verdict on why it ended, counted across the boss's wipes. A withheld "
    "verdict is counted under its reason rather than dropped, and a kill is not a wipe. "
    "Each verdict is a judgement on one attempt; this counts them and judges nothing again."
)

NEVER_TAKEN_DETAIL = (
    "Each compared pull names the abilities it took far more often than the reference kills "
    "did, and how many of those kills took each one at all. This counts the compared pulls "
    "naming an ability no reference kill took, never its hits, and names one only where more "
    "than half of them reported it. It states a difference, not a mistake: whether any landing "
    "could have been prevented is not something the log records."
)

OVERLANDING_DETAIL = (
    "Each compared pull names the abilities it took far more often than the reference kills "
    "did. This counts the compared pulls naming each ability, never its hits, and names one "
    "only where more than half of them reported it; one that every report said no reference "
    "kill took at all is named under its own finding instead. It states a difference, not a "
    "mistake: whether any landing could have been prevented is not something the log records."
)

_CERTAINTY = (Confidence.INFERRED, Confidence.DERIVED, Confidence.MEASURED)
"""Least certain first, so the lowest index is the weakest claim."""


def _least_certain(confidences: Iterable[Confidence]) -> Confidence:
    return min(confidences, key=_CERTAINTY.index)


def _kill_speed(
    attempts: Sequence[Encounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> Finding | None:
    """The kill's time and pace, lifted to the boss, or nothing on a boss that never died.

    Only the first drawn kill is read: a boss is killed once a night, and a
    kill whose pull did not load has no findings to read. A pull's pace
    carries the same id on a wipe, so the kill is found by the encounter, never
    by the findings.
    """
    kill = next((one for one in attempts if one.kill and one.fight_id in pull_findings), None)
    if kill is None:
        return None
    fight_id = kill.fight_id
    found = pull_findings.get(fight_id, ())
    kill_time = next((one for one in found if one.id == KILL_TIME_ID), None)
    pace = next((one for one in found if one.id == PACE_ID), None)
    lead = kill_time or pace
    if lead is None:
        return None

    # Whichever reading titles the rollup brings its own evidence along; a
    # pace beside a kill time is named by its title, which the rollup does
    # not otherwise carry.
    evidence = [f"On the kill, fight {fight_id}", *lead.evidence]
    if kill_time is not None and pace is not None:
        evidence.append(f"Damage pace: {pace.title}")
    return Finding(
        id=KILL_SPEED_ID,
        title=lead.title,
        detail=KILL_SPEED_DETAIL,
        confidence=_least_certain(one.confidence for one in (kill_time, pace) if one is not None),
        evidence=tuple(evidence),
    )


def _verdicts(
    attempts: Sequence[Encounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> Finding | None:
    """How many of the boss's wipes each verdict covered, withheld ones by their reason.

    A wipe whose pull was never drawn wrote no verdict to count, and is counted
    as withheld under `PULL_NOT_LOADED` rather than dropped, so the rollup's
    denominator is every wipe the boss had.
    """
    by_kind: dict[str, list[int]] = defaultdict(list)
    by_reason: dict[str, list[int]] = defaultdict(list)
    for one in attempts:
        if one.kill:
            continue
        fight_id = one.fight_id
        if fight_id not in pull_findings:
            by_reason[PULL_NOT_LOADED].append(fight_id)
            continue
        verdict = next((found for found in pull_findings[fight_id] if verdict_kind(found)), None)
        if verdict is None:
            # Not reached from `wowperf night`: `analyse_encounter` hands every
            # drawn wipe `classify_attempt`'s verdict or its withheld notice. A
            # caller passing a drawn wipe's findings without either has given
            # this nothing to count, and it counts nothing.
            continue
        kind = verdict_kind(verdict)
        if kind == "withheld":
            # `attempt_shape._withheld` gives every notice its reason as its one
            # evidence line.
            by_reason[verdict.evidence[0]].append(fight_id)
        else:
            by_kind[kind].append(fight_id)

    total = sum(len(ids) for ids in by_kind.values()) + sum(
        len(ids) for ids in by_reason.values()
    )
    if total == 0:
        return None
    wipes = quantity(total, "wipe", "wipes")

    kinds = sorted(by_kind.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    reasons = sorted(by_reason.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    evidence = tuple(
        f"{kind}: {len(ids)} of {wipes} ({fight_ranges(ids)})" for kind, ids in kinds
    ) + tuple(
        f"withheld, {reason}: {len(ids)} of {wipes} ({fight_ranges(ids)})"
        for reason, ids in reasons
    )

    if kinds:
        kind, ids = kinds[0]
        top = len(ids)
        title = f"{top} of {wipes} ended on {verdict_words(kind)}"
    else:
        top = 0
        title = f"No wipe's verdict could be read, of {wipes}"
    return Finding(
        id=VERDICTS_ID,
        title=title,
        detail=VERDICTS_DETAIL,
        # A read verdict is the one inferred finding counted here; a rollup of
        # withheld notices alone states only what the report lacked.
        confidence=Confidence.INFERRED if kinds else Confidence.MEASURED,
        evidence=evidence,
        quantifier=quantifier_for(top, total),
    )


def _reported(
    compared: Sequence[Encounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> tuple[dict[int, str], dict[int, list[int]], set[int]]:
    """Each ability's name and compared pulls, and those not reported never taken every time.

    Each pull counts once, however many of its findings name the ability. The
    returned set holds every ability some report did not read as one no
    reference took -- a single-reference reading, which counts no references,
    among them -- so an ability outside it was reported, every time, as one no
    reference took.
    """
    names: dict[int, str] = {}
    pulls: dict[int, list[int]] = defaultdict(list)
    taken: set[int] = set()
    for one in compared:
        seen: set[int] = set()
        for found in pull_findings.get(one.fight_id, ()):
            if not found.id.startswith(MECHANICS_ABILITY_PREFIX) or found.ability_id is None:
                continue
            names.setdefault(found.ability_id, found.ability_name)
            if found.quantifier != NO_REFERENCE_TOOK_IT:
                taken.add(found.ability_id)
            if found.ability_id not in seen:
                seen.add(found.ability_id)
                pulls[found.ability_id].append(one.fight_id)
    return names, pulls, taken


def _kept_landing(
    finding_id: str,
    detail: str,
    ability_ids: Iterable[int],
    names: Mapping[int, str],
    pulls: Mapping[int, list[int]],
    total: int,
    *,
    head: Callable[[str, int, int], str],
    single: Callable[[str, int, int], str],
    several: Callable[[int], str],
) -> Finding | None:
    """The abilities among `ability_ids` reported in more than half of `total` compared pulls.

    The bar is `progression.repeat.ability`'s, and the one `quantifier_for`'s
    "most" names. The title counts every qualifying ability; only the evidence
    is capped at `MAX_REPEAT_ABILITIES`, and a cut list says so.
    """
    repeated = sorted(
        (one for one in ability_ids if len(pulls[one]) * 2 > total),
        key=lambda one: (-len(pulls[one]), names[one]),
    )
    if not repeated:
        return None
    # The title counts every ability that repeated; only the evidence is capped,
    # and a capped list says so, so a reader never takes the lines for the count.
    named = repeated[:MAX_REPEAT_ABILITIES]
    cut_line = capped_line(len(repeated))
    lone = named[0] if len(repeated) == 1 else None
    top = len(pulls[named[0]])
    return Finding(
        id=finding_id,
        title=(
            single(names[lone], top, total) if lone is not None else several(len(repeated))
        ),
        detail=detail,
        confidence=Confidence.DERIVED,
        evidence=tuple(
            f"{head(names[one], len(pulls[one]), total)} ({fight_ranges(pulls[one])})"
            for one in named
        )
        + (() if cut_line is None else (cut_line,)),
        ability_id=lone,
        ability_name=names[lone] if lone is not None else "",
        quantifier=quantifier_for(top, total),
    )


def _over_landing(
    attempts: Sequence[Encounter],
    pull_findings: Mapping[int, Sequence[Finding]],
    mechanics_compared: frozenset[int],
) -> tuple[Finding | None, Finding | None]:
    """What kept landing that no reference kill took, then what landed more often than theirs.

    Both count the compared pulls only: a pull whose sample drew no member
    compared nothing, so it is left out of the denominator rather than counted
    as a pull where nothing over-landed. With fewer than two compared pulls
    nothing can be said to keep landing, so neither fires. An ability whose
    reports disagree goes to the second: a mixed record never earns the
    stronger claim.
    """
    compared = [one for one in attempts if one.fight_id in mechanics_compared]
    if len(compared) < 2:
        return None, None
    names, pulls, taken = _reported(compared, pull_findings)
    total = len(compared)
    never_taken = _kept_landing(
        NEVER_TAKEN_ID,
        NEVER_TAKEN_DETAIL,
        (one for one in pulls if one not in taken),
        names,
        pulls,
        total,
        head=lambda name, n, of: f"{name} landed in {n} of {of} compared attempts",
        single=lambda name, n, of: (
            f"{name} landed in {n} of {of} compared attempts, where no reference kill took it"
        ),
        several=lambda count: (
            f"{quantity(count, 'ability', 'abilities')} no reference kill took landed in "
            "most compared attempts"
        ),
    )
    over_landing = _kept_landing(
        OVERLANDING_ID,
        OVERLANDING_DETAIL,
        (one for one in pulls if one in taken),
        names,
        pulls,
        total,
        head=lambda name, n, of: f"{name} over-landed in {n} of {of} compared attempts",
        single=lambda name, n, of: f"{name} over-landed in {n} of {of} compared attempts",
        several=lambda count: (
            f"{quantity(count, 'ability', 'abilities')} over-landed in most compared attempts"
        ),
    )
    return never_taken, over_landing


def analyse_night_rollups(
    attempts: Sequence[Encounter],
    pull_findings: Mapping[int, Sequence[Finding]],
    mechanics_compared: frozenset[int],
) -> list[Finding]:
    """Kill speed, then why wipes ended, then what no reference took, then what
    over-landed: each where it fires.

    The order is the one design sections 5.2 and 10.3 set, and is fixed here.
    `attempts` are every attempt the boss's series holds, drawn or not,
    `pull_findings` every drawn pull's findings by fight id, and
    `mechanics_compared` the fight ids whose mechanics sample had members.

    A pull is drawn when its fight id is a key of `pull_findings`: `wowperf
    night` writes one for every pull it drew, an empty list included, so an
    attempt missing from it is one whose pull did not load.
    """
    never_taken, over_landing = _over_landing(attempts, pull_findings, mechanics_compared)
    candidates = (
        _kill_speed(attempts, pull_findings),
        _verdicts(attempts, pull_findings),
        never_taken,
        over_landing,
    )
    return [one for one in candidates if one is not None]

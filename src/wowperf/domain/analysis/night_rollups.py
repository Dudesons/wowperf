# ABOUTME: One boss's answers across its pulls: how fast it died, why wipes ended, what over-landed.
# ABOUTME: Each rollup counts findings the pulls already carry; none reads the log a second time.

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from wowperf.domain.analysis.attempt_shape import verdict_kind, verdict_words
from wowperf.domain.analysis.progression_repeats import MAX_REPEAT_ABILITIES
from wowperf.domain.comparison.kill_time import KILL_TIME_ID
from wowperf.domain.comparison.pace import PACE_ID
from wowperf.domain.encounter import LoadedEncounter
from wowperf.domain.findings import (
    Confidence,
    Finding,
    fight_ranges,
    quantifier_for,
    quantity,
)

KILL_SPEED_ID = "progression.lead.kill_speed"
VERDICTS_ID = "progression.lead.verdicts"
OVERLANDING_ID = "progression.lead.overlanding"

MECHANICS_ABILITY_PREFIX = "mechanics.ability."

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

OVERLANDING_DETAIL = (
    "Each compared pull names the abilities it took far more often than the reference kills "
    "did. This counts the compared pulls naming each ability, never its hits, and names only "
    "an ability more than one of them reported. It states a difference, not a mistake: "
    "whether any landing could have been prevented is not something the log records."
)

_CERTAINTY = (Confidence.INFERRED, Confidence.DERIVED, Confidence.MEASURED)
"""Least certain first, so the lowest index is the weakest claim."""


def _least_certain(confidences: Iterable[Confidence]) -> Confidence:
    return min(confidences, key=_CERTAINTY.index)


def _kill_speed(
    attempts: Sequence[LoadedEncounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> Finding | None:
    """The kill's time and pace, lifted to the boss, or nothing on a boss that never died.

    Only the first kill is read: a boss is killed once a night. A pull's pace
    carries the same id on a wipe, so the kill is found by the encounter, never
    by the findings.
    """
    kill = next((one for one in attempts if one.encounter.kill), None)
    if kill is None:
        return None
    fight_id = kill.encounter.fight_id
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
    attempts: Sequence[LoadedEncounter], pull_findings: Mapping[int, Sequence[Finding]]
) -> Finding | None:
    """How many of the boss's wipes each verdict covered, withheld ones by their reason."""
    by_kind: dict[str, list[int]] = defaultdict(list)
    by_reason: dict[str, list[int]] = defaultdict(list)
    for one in attempts:
        if one.encounter.kill:
            continue
        fight_id = one.encounter.fight_id
        verdict = next(
            (found for found in pull_findings.get(fight_id, ()) if verdict_kind(found)), None
        )
        if verdict is None:
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


def _overlanding(
    attempts: Sequence[LoadedEncounter],
    pull_findings: Mapping[int, Sequence[Finding]],
    mechanics_compared: frozenset[int],
) -> Finding | None:
    """Abilities more than one compared pull reported as over-landing, counted by pull.

    The threshold is `repeat_killing_blow`'s: an ability reported in two or more
    pulls, its evidence capped at `MAX_REPEAT_ABILITIES` while its title counts
    every such ability. Each pull counts once, however many
    of its findings name the ability, so two pulls reporting it are also the
    two compared pulls that rule asks for. A pull whose sample drew no member
    compared nothing, so it is left out of the denominator rather than counted
    as a pull where nothing over-landed.
    """
    compared = [one for one in attempts if one.encounter.fight_id in mechanics_compared]
    names: dict[int, str] = {}
    pulls_by_ability: dict[int, list[int]] = defaultdict(list)
    for one in compared:
        fight_id = one.encounter.fight_id
        reported = {
            found.ability_id: found.ability_name
            for found in pull_findings.get(fight_id, ())
            if found.id.startswith(MECHANICS_ABILITY_PREFIX) and found.ability_id is not None
        }
        for ability_id, name in reported.items():
            names.setdefault(ability_id, name)
            pulls_by_ability[ability_id].append(fight_id)

    repeated = sorted(
        (ability_id for ability_id, ids in pulls_by_ability.items() if len(ids) >= 2),
        key=lambda ability_id: (-len(pulls_by_ability[ability_id]), names[ability_id]),
    )
    if not repeated:
        return None
    # The title counts every ability that repeated; only the evidence is capped,
    # and a capped list says so, so a reader never takes the lines for the count.
    named = repeated[:MAX_REPEAT_ABILITIES]
    cut = (
        (
            "The evidence lists the "
            f"{quantity(MAX_REPEAT_ABILITIES, 'ability', 'abilities')} most reported",
        )
        if len(repeated) > len(named)
        else ()
    )

    total = len(compared)
    heads = tuple(
        f"{names[ability_id]} over-landed in {len(pulls_by_ability[ability_id])} of {total} "
        "compared attempts"
        for ability_id in named
    )
    single = named[0] if len(repeated) == 1 else None
    return Finding(
        id=OVERLANDING_ID,
        title=(
            heads[0]
            if single is not None
            else f"{len(repeated)} abilities over-landed in more than one compared attempt"
        ),
        detail=OVERLANDING_DETAIL,
        confidence=Confidence.DERIVED,
        evidence=tuple(
            f"{head} ({fight_ranges(pulls_by_ability[ability_id])})"
            for head, ability_id in zip(heads, named, strict=True)
        ) + cut,
        ability_id=single,
        ability_name=names[single] if single is not None else "",
        quantifier=quantifier_for(len(pulls_by_ability[named[0]]), total),
    )


def analyse_night_rollups(
    attempts: Sequence[LoadedEncounter],
    pull_findings: Mapping[int, Sequence[Finding]],
    mechanics_compared: frozenset[int],
) -> list[Finding]:
    """Kill speed, then why wipes ended, then what kept over-landing: each where it fires.

    The order is design section 5.2's and is fixed here. `attempts` are one
    boss's drawn pulls, `pull_findings` every drawn pull's findings by fight id,
    and `mechanics_compared` the fight ids whose mechanics sample had members.
    """
    candidates = (
        _kill_speed(attempts, pull_findings),
        _verdicts(attempts, pull_findings),
        _overlanding(attempts, pull_findings, mechanics_compared),
    )
    return [one for one in candidates if one is not None]

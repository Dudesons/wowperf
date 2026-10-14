# ABOUTME: Chooses one recent high key per dungeon, for one specialisation, from a character's runs.
# ABOUTME: A dungeon with nothing to read is left out with the reason, never silently dropped.

from collections import Counter
from collections.abc import Sequence

from wowperf.domain.character.model import ChosenRun, LeftOut, RankedRun, Selection, Zone

MYTHIC_PLUS_DIFFICULTY = 10
"""The one difficulty a Mythic+ zone is ranked at (wcl-api skill, 2026-10-14)."""

LEVELS_BELOW_TOP = 1
"""How far under the character's best key in a dungeon a run may sit and still be read."""

SELECTION_RULE = (
    "One run per dungeon: the most recent ranked run with a public log at the character's "
    f"highest keystone level in that dungeon or up to {LEVELS_BELOW_TOP} below it, timed or "
    "not, for one specialisation."
)


def require_mythic_plus(zone: Zone) -> None:
    if zone.difficulty_ids != (MYTHIC_PLUS_DIFFICULTY,):
        raise ValueError(
            f"Zone {zone.zone_id} ({zone.name}) is not a Mythic+ zone; "
            "the character command reads Mythic+ runs only"
        )


def choose_spec(runs: Sequence[RankedRun], requested: str | None) -> str:
    """The requested spec, or the one with the most ranked runs, then the latest run."""
    counts = Counter(run.spec for run in runs)
    if not counts:
        raise ValueError("This character has no ranked Mythic+ runs in this zone")
    if requested is not None:
        for spec in counts:
            if spec.casefold() == requested.casefold():
                return spec
        raise ValueError(
            f"No ranked runs as {requested!r}; ranked as: {', '.join(sorted(counts))}"
        )
    latest = {spec: max(run.start_time_ms for run in runs if run.spec == spec) for spec in counts}
    return max(counts, key=lambda spec: (counts[spec], latest[spec]))


def select_runs(zone: Zone, runs: Sequence[RankedRun], spec: str | None = None) -> Selection:
    chosen_spec = choose_spec(runs, spec)
    chosen: list[ChosenRun] = []
    left_out: list[LeftOut] = []
    for dungeon in zone.dungeons:
        mine = [
            run for run in runs
            if run.encounter_id == dungeon.encounter_id and run.spec == chosen_spec
        ]
        if not mine:
            left_out.append(
                LeftOut(dungeon=dungeon.name, reason=f"no ranked run as {chosen_spec}")
            )
            continue
        top = max(run.keystone_level for run in mine)
        floor = top - LEVELS_BELOW_TOP
        best: ChosenRun | None = None
        for run in mine:
            if run.keystone_level < floor or run.report_code is None or run.fight_id is None:
                continue
            if best is None or run.start_time_ms > best.start_time_ms:
                best = ChosenRun(
                    dungeon=dungeon.name,
                    encounter_id=dungeon.encounter_id,
                    keystone_level=run.keystone_level,
                    start_time_ms=run.start_time_ms,
                    report_code=run.report_code,
                    fight_id=run.fight_id,
                )
        if best is None:
            left_out.append(LeftOut(
                dungeon=dungeon.name,
                reason=f"no run at +{top} or +{floor} has a public report",
            ))
            continue
        chosen.append(best)
    return Selection(spec=chosen_spec, chosen=tuple(chosen), left_out=tuple(left_out))

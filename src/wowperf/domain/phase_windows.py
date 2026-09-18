# ABOUTME: Which named phase an instant of a boss fight fell in.
# ABOUTME: Reads transitions by time, never by position or by highest id reached.

from collections import Counter

from wowperf.domain.base import Frozen
from wowperf.domain.events import DamageTakenEvent
from wowperf.domain.phases import Phase, PhaseTransition


def phase_at(
    phases: tuple[Phase, ...],
    transitions: tuple[PhaseTransition, ...],
    timestamp_ms: int,
) -> Phase | None:
    """The phase an instant fell in, or None where the encounter names none.

    **A transition list is not a ladder.** One measured attempt ran 1, 2, 1, 2,
    1, 2, 1 (skill file, 2026-09-18), so the phase at an instant is the one the
    *latest* transition at or before it names -- never the highest id seen, and
    never the last element of the list.

    Transitions are read by `start_ms` rather than by their order in the tuple,
    because nothing in the API's contract promises the list is sorted and
    sorting costs nothing at these lengths.

    **Transitions tile the fight.** Measured 2026-09-18 across 104 fights
    carrying transitions, every first transition sat exactly at its fight's
    start, so an instant inside a fight always lands in a window. An instant
    before the first transition is answered None rather than assumed into the
    first listed phase -- it does not arise in practice, and guessing would be
    the kind of quiet fabrication the confidence badges exist to prevent.

    A transition naming an id the phase list does not carry is answered None
    for the same reason: encounter 3470 reported `lastPhase: 2` against
    transitions ending in 3, so the two vocabularies are known to disagree.
    """
    if not phases or not transitions:
        return None
    by_id = {phase.id: phase for phase in phases}
    current: Phase | None = None
    for transition in sorted(transitions, key=lambda one: one.start_ms):
        if transition.start_ms > timestamp_ms:
            break
        current = by_id.get(transition.id)
    return current


class PhaseShare(Frozen):
    """Where one ability's landings concentrated, and how concentrated they were.

    Carries `landings` and `total` rather than only a share, because the finding
    states both: "27 landings, 19 of them in Stage Two" is checkable and "70% in
    Stage Two" is not.
    """

    phase: Phase
    landings: int
    total: int


def dominant_phase_by_ability(
    events: tuple[DamageTakenEvent, ...],
    phases: tuple[Phase, ...],
    transitions: tuple[PhaseTransition, ...],
) -> dict[int, PhaseShare]:
    """Per ability id, the phase most of its landings fell in.

    This is the join that lets a whole-fight comparison name a phase. The
    comparison's own input is an `AbilityTakenRow` table carrying no
    timestamps, and the event stream carrying them is fetched anyway, so the
    phase is read here and handed over rather than teaching the comparison to
    read events.

    **Our side only.** The reference side of any comparison is a table with no
    timestamps at all, so nothing here may be used to claim a reference kill
    spent its landings differently -- see the design's section 9.

    An ability whose landings all fall outside every phase window is absent
    from the result rather than present with a null phase: a caller asking
    "which phase" gets an answer or gets nothing.
    """
    counts: dict[int, Counter[int]] = {}
    by_id = {phase.id: phase for phase in phases}
    for event in events:
        placed = phase_at(phases, transitions, event.timestamp_ms)
        if placed is None:
            continue
        counts.setdefault(event.ability_id, Counter())[placed.id] += 1

    shares: dict[int, PhaseShare] = {}
    for ability_id, tally in counts.items():
        phase_id, landings = max(tally.items(), key=lambda pair: (pair[1], -pair[0]))
        shares[ability_id] = PhaseShare(
            phase=by_id[phase_id], landings=landings, total=sum(tally.values())
        )
    return shares

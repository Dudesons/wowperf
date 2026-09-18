# ABOUTME: Which named phase an instant of a boss fight fell in.
# ABOUTME: Reads transitions by time, never by position or by highest id reached.

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

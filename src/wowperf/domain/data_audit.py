# ABOUTME: Checks the hand-maintained ability data against the ability ids real logs cast.
# ABOUTME: An entry never cast, whose name the logs cast under another id, reads as a wrong id.

from collections.abc import Mapping, Sequence

from wowperf.domain.base import Frozen


class AuditEntry(Frozen):
    """One ability as a data file lists it: which file, which specialisation, which id."""

    file: str
    spec: str
    ability_id: int
    name: str


class NeverCast(Frozen):
    """One entry no cast row carries, and the same-named ids the logs did cast.

    `cast_as` pairs each such id with how many cast rows carry it, most cast
    first and the lowest id on a tie. Empty means the logs never cast that name
    under any id -- which a talent nobody took explains as well as a wrong id,
    so the audit reports it and does not guess between the two.
    """

    entry: AuditEntry
    cast_as: tuple[tuple[int, int], ...] = ()


def never_cast(
    entries: Sequence[AuditEntry],
    casts: Mapping[int, int],
    named: Mapping[str, frozenset[int]],
) -> tuple[NeverCast, ...]:
    """Every entry whose id no cast row carries, in the order the entries came.

    `casts` counts cast rows by ability id. `named` maps a case-folded ability
    name to every id a report's ability table gives that name. An id a table
    names but no row casts is not offered as a replacement: a table lists what
    a report mentions, and only a cast row says what a press logs.
    """
    found: list[NeverCast] = []
    for entry in entries:
        if casts.get(entry.ability_id, 0):
            continue
        others = named.get(entry.name.casefold(), frozenset()) - {entry.ability_id}
        cast_as = sorted(
            ((other, casts[other]) for other in others if casts.get(other, 0)),
            key=lambda pair: (-pair[1], pair[0]),
        )
        found.append(NeverCast(entry=entry, cast_as=tuple(cast_as)))
    return tuple(found)


def audit_lines(entries: Sequence[AuditEntry], found: Sequence[NeverCast]) -> tuple[str, ...]:
    """The audit as the command prints it: one heading per file, one line per entry never cast."""
    lines: list[str] = []
    for file in dict.fromkeys(entry.file for entry in entries):
        total = sum(entry.file == file for entry in entries)
        missing = [one for one in found if one.entry.file == file]
        lines.append(f"{file}: {len(missing)} of {total} entries never cast")
        for one in missing:
            entry = one.entry
            where = f"  {entry.spec}  {entry.name}  {entry.ability_id}"
            if one.cast_as:
                cast = ", ".join(f"{other} x{count}" for other, count in one.cast_as)
                lines.append(f"{where}: never cast; the logs cast it as {cast}")
            else:
                lines.append(f"{where}: never cast, under this or any other id of that name")
    return tuple(lines)

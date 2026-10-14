# ABOUTME: The hand-kept lists of aura ids that are one cause, and the fold of auras by them.
# ABOUTME: A group reads as one aura under its main id, so one cause is one row and one gap slot.

from collections.abc import Sequence

from pydantic import model_validator

from wowperf.domain.auras import Aura, AuraBand, PlayerAuras, clipped_bands
from wowperf.domain.base import Frozen


class AuraGroups(Frozen):
    """Aura ids that are one cause, each group's first id being its main one.

    A tuple of tuples rather than a mapping, like every other curated list
    here: the domain layer's values are frozen and hashable, and a dict is
    neither. The aura table carries no source for a row, so which ids share a
    cause is data (`data/aura_groups.toml`) and not something the log says.

    A group of one id would fold nothing, and an id in two groups would make the
    fold's answer depend on which it met first, so both are refused when the
    value is built, whoever builds it.
    """

    groups: tuple[tuple[int, ...], ...] = ()

    @model_validator(mode="after")
    def _well_formed(self) -> "AuraGroups":
        seen: set[int] = set()
        for group in self.groups:
            if len(group) < 2:
                raise ValueError(f"an aura group needs at least two ids, got {list(group)}")
            for ability_id in group:
                if group.count(ability_id) > 1:
                    raise ValueError(f"ability id {ability_id} is listed twice in one aura group")
                if ability_id in seen:
                    raise ValueError(f"ability id {ability_id} is in more than one aura group")
                seen.add(ability_id)
        return self


def _named(names: Sequence[str]) -> str:
    """Every member's name, the first leading: "A", "A, with B", "A, with B and C"."""
    first, *rest = names
    if not rest:
        return first
    tail = rest[0] if len(rest) == 1 else f"{', '.join(rest[:-1])} and {rest[-1]}"
    return f"{first}, with {tail}"


def _one_aura(present: Sequence[Aura], main_id: int) -> Aura:
    """The members one side carried, as one aura under the group's main id.

    `present` is in the group's order, so its first member is the main one when
    the side carried it and the first of the others when it did not. That
    member's icon and use count stand for the group.

    Its bands are the union of the members' and its total is that union's
    length, so a stretch two members share counts once. `clipped_bands` does
    the merging; the window it clips to is the extent of the bands themselves,
    which clips nothing.
    """
    first = present[0]
    every_band = [band for aura in present for band in aura.bands]
    if every_band:
        union = clipped_bands(
            first.model_copy(update={"bands": tuple(every_band)}),
            min(band.start_ms for band in every_band),
            max(band.end_ms for band in every_band),
        )
    else:
        union = ()
    return Aura(
        ability_id=main_id,
        name=_named([aura.name for aura in present]),
        total_uptime_ms=sum(end - start for start, end in union),
        uses=first.uses,
        icon=first.icon,
        bands=tuple(AuraBand(start_ms=start, end_ms=end) for start, end in union),
    )


def merge_aura_groups(auras: PlayerAuras, groups: AuraGroups) -> PlayerAuras:
    """One player's auras with each group's members folded into a single aura.

    The folded aura always carries the group's main id, even where the main is
    absent on this side, so that two sides which carried different members key
    the same row. It sits where the first member the table listed sat; an aura
    in no group, and a group no member of which is carried, pass through
    untouched and in order.
    """
    if not groups.groups:
        return auras
    group_of = {
        ability_id: index for index, group in enumerate(groups.groups) for ability_id in group
    }
    by_id = {aura.ability_id: aura for aura in reversed(auras.on_self)}
    on_self: list[Aura] = []
    emitted: set[int] = set()
    for aura in auras.on_self:
        index = group_of.get(aura.ability_id)
        if index is None:
            on_self.append(aura)
            continue
        if index in emitted:
            continue
        emitted.add(index)
        group = groups.groups[index]
        present = [by_id[ability_id] for ability_id in group if ability_id in by_id]
        on_self.append(_one_aura(present, group[0]))
    return auras.model_copy(update={"on_self": tuple(on_self)})

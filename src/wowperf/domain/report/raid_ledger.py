# ABOUTME: Where each raid finding family lands, mirroring ledger.py's PLACEMENTS for the
# ABOUTME: Mythic+ page but naming RaidReport's own fields instead of Report's.

RAID_DECOMPOSITION_IDS = ("deaths.total",)
"""A raid has one figure that contains others. `compare.duration` and
`time.residual` are keystone shapes with no raid meaning."""

RAID_NESTS_INSIDE = (
    ("deaths.single.", "deaths.total"),
    ("deaths.chain.", "deaths.total"),
    ("deaths.repeat.", "deaths.total"),
)
"""Which figures are already contained by `deaths.total`, the raid path's only decomposition.

A raid has no route and no timer, so the Mythic+ table's `time.gap.`,
`compare.downtime` and `compare.route.skipped.` entries have nothing here to
nest inside.
"""


RAID_PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("defensives.unused.", "death_rows"),
    ("consumables.", "death_rows"),
    ("deaths.", "death_rows"),
    ("mechanics.", "mechanics_rows"),
    ("players.damage.", "mechanics_rows"),
    ("interrupts.", "interrupts"),
    ("compare.damage.", "damage_rows"),
    ("compare.rank", "damage_rows"),
    ("defensives.", "group_rows"),
)
"""Which tab's rows a raid finding family lands in: the first prefix that matches wins.

Order is the rule, and the narrow families come first, exactly as in the
Mythic+ table beside this one: `defensives.unused.` is a death-shaped claim
while `defensives.ceiling.` and `defensives.never.` are claims about the whole
fight and fall through to the bare `defensives.`.

`players.damage.` sits on the mechanics tab rather than a player card, unlike
Mythic+: design section 6.9 measures it per ability against the group median,
which is the same question section 6.8 asks, and the two read together.

The per-card families are in `RAID_COMPARISON_PREFIXES` and are deliberately
absent here, as they are in the Mythic+ table.
"""

RAID_COMPARISON_PREFIXES = (
    "compare.spells.",
    "compare.talents",
    "compare.uptime.",
    "compare.gear.",
    "compare.stats.",
    "compare.consumables.",
    "compare.parse.unavailable",
)
"""Families that belong on a raider's card rather than in the ledger.

Which card is decided by the slug the finding carries, never by who the
subject is -- Task 2 is what puts a slug on every one of them.
`compare.parse.unavailable` is here rather than in the Mythic+ table's
`group_rows`, because on a wipe every raider gets one and a single shared row
beneath the cards would say it once for twenty people.
"""


def _raid_field_for(finding_id: str) -> str | None:
    """The raid sibling of `ledger._field_for`, matching against `RAID_PLACEMENTS`.

    Kept as its own function rather than a call into `ledger._field_for` with
    `placements=RAID_PLACEMENTS`: that keyword argument exists for `place_rows`
    to take either table, not for one private lookup to wrap another.
    """
    return next(
        (field for prefix, field in RAID_PLACEMENTS if finding_id.startswith(prefix)), None
    )

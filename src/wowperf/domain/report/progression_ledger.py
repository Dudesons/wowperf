# ABOUTME: Where each progression finding family lands, mirroring raid_ledger.py's table.
# ABOUTME: A family absent from the table reaches the Summary's catch-all, never nowhere.

PROGRESSION_PLACEMENTS: tuple[tuple[str, str], ...] = (
    ("progression.best.", "best_rows"),
    ("progression.best", "best_rows"),
    ("progression.repeat.", "repeat_rows"),
    ("progression.collapse", "repeat_rows"),
    ("progression.cluster", "attempt_rows"),
    ("progression.movement", "attempt_rows"),
    ("progression.attempts.", "attempt_rows"),
)
"""Which tab's rows a progression finding family lands in: the first prefix
that matches wins.

Order is the rule and the narrow families come first, exactly as in the two
tables beside this one. `progression.best.` and `progression.best` name the
same field today, so reversing them changes nothing -- they are written in
that order anyway, because the day a Layer 3 finding wants a tab of its own is
the day an unordered table quietly sends it to the wrong one.

`progression.best` -- Layer 1's "which attempt went deepest" -- sits on the
Best attempt tab rather than with the cluster, so that tab always opens on the
attempt it is about.

There is no decomposition table beside this one. A progression finding costs
no seconds, so no figure here contains another and nothing can be nested.
"""


def progression_field_for(finding_id: str) -> str | None:
    """The progression sibling of `ledger._field_for`.

    `None` for an id the table does not cover, which is what sends it to
    `build_observations` and onto the Summary. A default field here would put a
    new family on a tab nobody chose and look deliberate doing it.
    """
    return next(
        (field for prefix, field in PROGRESSION_PLACEMENTS if finding_id.startswith(prefix)),
        None,
    )

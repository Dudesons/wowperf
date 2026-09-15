# ABOUTME: Tests for the players module.
# ABOUTME: Domain-level player analysis and slug generation.

from wowperf.domain.model import Player
from wowperf.domain.report.players import slugs_by_actor


def test_a_roster_is_all_the_slugs_need() -> None:
    """The function reads `players` and nothing else, so it takes `players`.

    A raid has no `Run` to hand it. Narrowing rather than widening is this
    project's rule at every seam plan 3a touched, and the alternative --
    a second function, or an `Encounter | Run` union -- leaves the wrong
    argument representable.
    """
    players = (
        Player(
            actor_id=11, name="Emberkin", class_name="Mage", spec="Arcane",
            item_level=680
        ),
        Player(
            actor_id=12, name="Stonewake", class_name="DeathKnight", spec="Blood",
            item_level=680
        ),
    )

    slugs = slugs_by_actor(players)

    assert slugs == {11: "emberkin-0", 12: "stonewake-1"}


def test_two_names_that_reduce_to_one_slug_stay_apart() -> None:
    """`Bríala` and `Briala` decompose to the same slug, so the index separates them.

    The index is the roster's own order, not the order cards are drawn in, so
    a deep link survives a re-run that named a different subject. Without the
    suffix both players own the fragment id `briala` and the page sends every
    link to whichever the browser picks first.
    """
    players = (
        Player(
            actor_id=21, name="Bríala", class_name="Priest", spec="Discipline",
            item_level=680
        ),
        Player(
            actor_id=22, name="Briala", class_name="Priest", spec="Shadow",
            item_level=680
        ),
    )

    slugs = slugs_by_actor(players)

    assert slugs[21] != slugs[22]
    assert set(slugs.values()) == {"briala-0", "briala-1"}

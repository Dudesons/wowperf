# ABOUTME: The attempt floor is a claim about the data, so a test holds it to one.
# ABOUTME: A floor nobody measured is a magic number; this pins what was measured.

from wowperf.domain.progression import MIN_ATTEMPT_SECONDS


def test_the_floor_keeps_the_shortest_raid_attempt_measured() -> None:
    """The shortest of 99 measured raid attempts ran 18.68s; the floor must sit under it."""
    assert MIN_ATTEMPT_SECONDS < 18.68


def test_the_floor_is_large_enough_to_filter_a_real_reset() -> None:
    """A floor this small would just be MIN_PACK_SECONDS's segmentation-artifact scale reused."""
    assert MIN_ATTEMPT_SECONDS > 5.0


def test_the_floor_records_how_it_was_measured() -> None:
    """A floor with no recorded population is the magic number this avoids."""
    import wowperf.domain.progression as module

    note = getattr(module, "_MIN_ATTEMPT_SECONDS_NOTE", "")
    assert "2026-" in note, "the floor's note must carry the date it was measured"
    assert len(note) > 200, "the note must record the distribution, not just assert one"

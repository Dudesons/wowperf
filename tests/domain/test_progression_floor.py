# ABOUTME: The attempt floor is a claim about the data, so a test holds it to one.
# ABOUTME: A floor nobody measured is a magic number; this pins what was measured.

from wowperf.domain.progression import MIN_ATTEMPT_SECONDS


def test_the_floor_keeps_the_shortest_confirmed_real_attempt() -> None:
    """A raid wipe at 47.17s moved the boss to 87.86% remaining -- shallow, but real combat."""
    assert MIN_ATTEMPT_SECONDS < 47.17


def test_the_floor_excludes_the_longest_confirmed_reset() -> None:
    """A 41.01s raid wipe left the boss at 97.33% remaining: near nothing done, under a minute."""
    assert MIN_ATTEMPT_SECONDS > 41.01


def test_the_floor_records_how_it_was_measured() -> None:
    """A floor with no recorded population is the magic number this avoids."""
    import wowperf.domain.progression as module

    note = getattr(module, "_MIN_ATTEMPT_SECONDS_NOTE", "")
    assert "2026-" in note, "the floor's note must carry the date it was measured"
    assert len(note) > 200, "the note must record the distribution, not just assert one"

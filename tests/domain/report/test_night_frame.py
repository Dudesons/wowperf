# ABOUTME: The night page's frame: the one fact above its dropdowns, and each pull's subject.
# ABOUTME: A roster the page cannot open a card on is refused by name, never by IndexError.

import pytest

from tests.domain.test_progression import an_attempt
from wowperf.domain.model import Player
from wowperf.domain.night import LoadedNight, Night
from wowperf.domain.report.night_frame import build_night_header, night_subject

REPORT_CODE = "TESTCODE00000000"

ROSTER = (
    Player(actor_id=1, name="Emberkin", class_name="Mage", spec="Arcane", item_level=700),
    Player(actor_id=2, name="Stonewake", class_name="DeathKnight", spec="Blood", item_level=690),
)


def test_the_header_carries_the_report_code_of_a_night_that_loaded_nothing() -> None:
    """The report code is read off the `Night`, not off a pull.

    A night whose every pull failed has no pull to read it from, and that is
    the night whose page most needs to name the report it covers.
    """
    header = build_night_header(LoadedNight(night=Night(report_code=REPORT_CODE)))

    assert header.report_code == REPORT_CODE


def test_a_pull_with_no_roster_is_refused_by_name() -> None:
    """A bare `IndexError` would name nothing and kill the whole page.

    One pull failing to load shrinks the night rather than failing it, and it
    is named with its reason. A build-time crash on one pull would undo that
    one layer up, so the refusal at least says which pull to go and look at.
    """
    rosterless = an_attempt(17, 50.0, 200.0, players=(), owner_name="stonewake")

    with pytest.raises(ValueError, match="17"):
        night_subject(rosterless)


def test_a_roster_the_owner_is_on_is_not_refused() -> None:
    """The other half: the refusal fires on an empty roster and on nothing else."""
    pull = an_attempt(17, 50.0, 200.0, players=ROSTER, owner_name="stonewake")

    assert night_subject(pull).name == "Stonewake"

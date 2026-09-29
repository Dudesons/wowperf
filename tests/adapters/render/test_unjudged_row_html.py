# ABOUTME: A defensive the card cannot judge reaches the Deaths panel as its builder wrote it.
# ABOUTME: No golden holds such a row, so this is the one render test that draws it.

from markupsafe import escape

from tests.adapters.render.test_deaths_healers_html import mplus_html
from tests.adapters.render.test_raid_html_invariants import _panel
from tests.domain.report.test_build_deaths import BLOOD, a_death, a_loaded_with, owns_icebound
from tests.domain.report.test_build_frame import NO_CONSUMABLES
from wowperf.domain.report.deaths import build_deaths


def test_an_unjudged_row_is_drawn_with_its_state_and_its_sentence() -> None:
    loaded = a_loaded_with((a_death(1, 60_000),), ()).model_copy(
        update={"casts": owns_icebound(70_000)}
    )
    card = build_deaths(loaded, BLOOD, NO_CONSUMABLES)[0]
    [row] = card.availability[0].rows
    deaths = _panel(mplus_html(card), "tab-deaths")
    assert '<li class="unjudged">' in deaths
    assert str(escape(row.detail)) in deaths
    assert ">None<" not in deaths

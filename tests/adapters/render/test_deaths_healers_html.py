# ABOUTME: The Healers group reaches both pages' Deaths panel as its builder wrote it, alone.
# ABOUTME: Every string asserted is read off the built card, never typed a second time.

from markupsafe import escape

from tests.adapters.render.test_html_invariants import (
    COMPARED,
    SUBJECT,
    minimal_findings,
    minimal_loaded,
)
from tests.adapters.render.test_raid_html_invariants import _panel, a_built_raid_report
from tests.domain.report.test_build_deaths_healers import DRUID, card_for, cast
from tests.domain.report.test_build_frame import FETCHED, NO_CONSUMABLES, NO_DEFENSIVES
from wowperf.adapters.render.html import render, render_raid
from wowperf.domain.report.build import build_report
from wowperf.domain.report.model import DeathCard


def a_card() -> DeathCard:
    return card_for([
        cast(DRUID, 20, None, ability_id=740), cast(DRUID, 293, 3), cast(DRUID, 296, None),
    ])


def drawn_strings(card: DeathCard) -> list[str]:
    assert card.healers is not None
    group = card.healers
    strings = [group.title, group.note]
    for line in group.lines:
        strings += [line.holder, line.summary, *(row.detail for row in line.cooldowns)]
    return [str(escape(one)) for one in strings if one]


def mplus_html(card: DeathCard) -> str:
    report = build_report(
        minimal_loaded(), minimal_findings(), None, COMPARED, SUBJECT, None, FETCHED,
        NO_DEFENSIVES, NO_CONSUMABLES,
    )
    return render(report.model_copy(update={"deaths": (card,)}))


def test_the_healers_group_is_drawn_in_the_mythic_plus_deaths_panel_alone() -> None:
    card = a_card()
    html = mplus_html(card)
    deaths = _panel(html, "tab-deaths")
    for text in drawn_strings(card):
        assert text in deaths, text
    summary = str(escape(card.healers.lines[0].summary)) if card.healers else ""
    assert html.count(summary) == 1
    assert ">None<" not in deaths


def test_the_healers_group_is_drawn_in_the_raid_deaths_panel_alone() -> None:
    card = a_card()
    html = render_raid(a_built_raid_report().model_copy(update={"deaths": (card,)}))
    deaths = _panel(html, "tab-deaths")
    for text in drawn_strings(card):
        assert text in deaths, text
    summary = str(escape(card.healers.lines[0].summary)) if card.healers else ""
    assert html.count(summary) == 1
    assert ">None<" not in deaths


def test_both_badges_render_beside_what_they_qualify() -> None:
    card = a_card()
    deaths = _panel(mplus_html(card), "tab-deaths")
    healers = deaths[deaths.index('class="avail healers"'):]
    assert 'class="badge badge-measured"' in healers
    assert 'class="badge badge-derived"' in healers


def test_a_card_with_no_other_healer_draws_its_one_sentence() -> None:
    card = card_for([], dying=DRUID)
    deaths = _panel(mplus_html(card), "tab-deaths")
    assert card.healers is not None
    assert str(escape(card.healers.note)) in deaths
    assert 'class="healer-line"' not in deaths


def test_a_card_with_no_healers_group_draws_none_at_all() -> None:
    card = card_for([], roles=None)
    assert card.healers is None
    deaths = _panel(mplus_html(card), "tab-deaths")
    assert 'class="avail healers"' not in deaths

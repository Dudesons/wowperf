# ABOUTME: Tests that a run's shared explanation renders once, above the cards it covers.
# ABOUTME: The template only renders whichever field it is handed; build.py decided the run.

from tests.adapters.render.test_html import a_report, a_row
from wowperf.adapters.render.html import render

NOTE = "Both rates are casts per minute of boss pull time."


def a_run() -> tuple[object, ...]:
    """Three rows as `collapse_repeated_details` leaves them: one note, no details."""
    return (
        a_row("compare.spells.rate.0", detail="", group_note=NOTE),
        a_row("compare.spells.rate.1", detail=""),
        a_row("compare.spells.rate.2", detail=""),
    )


def test_the_shared_explanation_is_rendered_once_for_the_whole_run() -> None:
    html = render(a_report(route_rows=a_run()))

    assert html.count(NOTE) == 1


def test_the_note_precedes_the_first_card_it_covers() -> None:
    """Rendered inside the first card it would read as that card's own reason."""
    html = render(a_report(route_rows=a_run()))

    assert html.index(NOTE) < html.index('id="finding-compare.spells.rate.0"')


def test_a_row_whose_detail_was_hoisted_away_leaves_no_empty_paragraph() -> None:
    """An empty <p> is a blank line the reader cannot account for."""
    html = render(a_report(route_rows=a_run()))

    assert '<p class="detail"></p>' not in html


def test_a_row_that_kept_its_detail_still_renders_it() -> None:
    """Grouping must not be the reason an ungrouped finding loses its explanation."""
    html = render(a_report(route_rows=(a_row("time.gap.0", detail="Travel, not combat."),)))

    assert "Travel, not combat." in html


def test_the_group_note_spans_the_full_grid_row() -> None:
    # F7: `.findings` is a grid, and every direct child -- including this note
    # -- is a grid item. Without an explicit span the note takes one card's
    # own column instead of reading as an introduction to the cards after it.
    html = render(a_report(route_rows=a_run()))

    assert "grid-column: 1 / -1" in html

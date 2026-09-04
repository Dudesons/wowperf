# ABOUTME: Behaviour tests for turning what a user pastes into a report code and fight ID.
# ABOUTME: People paste full URLs with fragments, so bare codes and fragments both parse.

import pytest

from wowperf.urls import parse_report_url


def test_a_bare_report_code_parses_with_no_fight() -> None:
    assert parse_report_url("aBc123XyZ") == ("aBc123XyZ", None)


def test_a_report_url_yields_its_code() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ") == (
        "aBc123XyZ",
        None,
    )


def test_a_fight_fragment_is_read() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ#fight=7") == (
        "aBc123XyZ",
        7,
    )


def test_a_last_fight_fragment_means_no_explicit_fight() -> None:
    assert parse_report_url("https://www.warcraftlogs.com/reports/aBc123XyZ#fight=last") == (
        "aBc123XyZ",
        None,
    )


def test_something_that_is_not_a_report_is_rejected() -> None:
    with pytest.raises(ValueError, match="not a Warcraft Logs report"):
        parse_report_url("https://example.com/nope")


def test_a_fight_query_string_is_read() -> None:
    # A URL pasted straight from the browser's address bar: warcraftlogs.com puts the
    # fight number in the query string, not only in the #fight= fragment.
    assert parse_report_url(
        "https://www.warcraftlogs.com/reports/6Kx1P9GbNXrcLdHa?fight=36&type=damage-done"
    ) == ("6Kx1P9GbNXrcLdHa", 36)


def test_a_last_fight_query_string_means_no_explicit_fight() -> None:
    assert parse_report_url(
        "https://www.warcraftlogs.com/reports/aBc123XyZ?fight=last"
    ) == ("aBc123XyZ", None)


def test_a_fragment_overrides_a_query_string() -> None:
    # The fragment is what the browser's address bar shows last, so it wins.
    assert parse_report_url(
        "https://www.warcraftlogs.com/reports/aBc123XyZ?fight=5#fight=9"
    ) == ("aBc123XyZ", 9)

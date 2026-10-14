# ABOUTME: Behaviour tests for reading a pasted report code and fight ID, or a character page.
# ABOUTME: People paste full URLs with fragments, so bare codes and fragments both parse.

import pytest

from wowperf.urls import CharacterRef, parse_character_url, parse_report_url


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
        "https://www.warcraftlogs.com/reports/qRs789TuV?fight=36&type=damage-done"
    ) == ("qRs789TuV", 36)


def test_a_last_fight_query_string_means_no_explicit_fight() -> None:
    assert parse_report_url(
        "https://www.warcraftlogs.com/reports/aBc123XyZ?fight=last"
    ) == ("aBc123XyZ", None)


def test_a_fragment_overrides_a_query_string() -> None:
    # The fragment is what the browser's address bar shows last, so it wins.
    assert parse_report_url(
        "https://www.warcraftlogs.com/reports/aBc123XyZ?fight=5#fight=9"
    ) == ("aBc123XyZ", 9)


def test_a_character_url_yields_its_region_realm_name_and_zone() -> None:
    assert parse_character_url(
        "https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=55"
    ) == CharacterRef(region="eu", realm="argent-dawn", name="Emberkin", zone_id=55)


def test_a_character_url_without_a_zone_has_none() -> None:
    assert parse_character_url(
        "https://www.warcraftlogs.com/character/us/stormrage/Stonewake"
    ).zone_id is None


def test_an_accented_name_is_decoded() -> None:
    ref = parse_character_url("https://www.warcraftlogs.com/character/EU/Archimonde/Br%C3%ADala")
    assert ref == CharacterRef(region="eu", realm="archimonde", name="Bríala", zone_id=None)


def test_a_report_url_is_not_a_character_url() -> None:
    with pytest.raises(ValueError, match="not a Warcraft Logs character URL"):
        parse_character_url("https://www.warcraftlogs.com/reports/aBc123XyZ")


def test_a_zone_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a zone id"):
        parse_character_url("https://www.warcraftlogs.com/character/eu/argent-dawn/Emberkin?zone=x")

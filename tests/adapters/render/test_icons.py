# ABOUTME: The rules that decide what an icon file name is, and the store that keeps the bytes.
# ABOUTME: No network: every rule here is decided before a request would be made.

import base64
import os
from pathlib import Path
from unittest import mock

import pytest

from wowperf.adapters.render.icons import BlizzardIcons, IconStore, icon_filename


def test_a_plain_icon_name_is_accepted() -> None:
    assert icon_filename("spell_holy_magicalsentry.jpg") == "spell_holy_magicalsentry.jpg"


def test_a_query_suffix_is_stripped_so_two_spellings_name_one_file() -> None:
    assert icon_filename("ability_monk_chiexplosion.jpg?cachebust") == (
        "ability_monk_chiexplosion.jpg"
    )


def test_a_name_that_could_walk_out_of_the_cache_directory_is_refused() -> None:
    assert icon_filename("../../../etc/passwd.jpg") is None
    assert icon_filename("sub/dir/spell.jpg") is None


def test_a_name_that_is_not_a_jpg_is_refused() -> None:
    assert icon_filename("spell_holy_magicalsentry.png") is None
    assert icon_filename("") is None


def test_a_name_with_uppercase_letters_is_refused() -> None:
    assert icon_filename("Spell_Holy_MagicalSentry.jpg") is None


def test_the_store_reads_back_what_it_wrote(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    store.write("spell_a.jpg", b"\xff\xd8bytes")
    assert store.read("spell_a.jpg") == b"\xff\xd8bytes"


def test_an_unknown_file_reads_as_nothing_and_is_not_a_known_miss(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    assert store.read("spell_a.jpg") is None
    assert store.known_miss("spell_a.jpg") is False


def test_a_recorded_miss_is_remembered_so_it_is_asked_for_once(tmp_path: Path) -> None:
    store = IconStore(tmp_path)
    store.write_miss("spell_a.jpg")
    assert store.known_miss("spell_a.jpg") is True
    assert store.read("spell_a.jpg") is None


def test_an_interrupted_write_never_becomes_a_stored_icon(tmp_path: Path) -> None:
    """Content reaches the store only through the rename, so a torn write cannot be read.

    A process killed mid-write cannot be staged from inside the process. This
    drives the same seam instead: the rename fails, and nothing observable is
    left behind under the name nor as a stray temporary. This is the one
    failure mode the store never self-heals from: it expires nothing, so a
    leaked partial file would sit there and be embedded in every future report.
    """
    store = IconStore(tmp_path)

    with mock.patch.object(os, "replace", side_effect=OSError("interrupted")):
        with pytest.raises(OSError, match="interrupted"):
            store.write("spell_a.jpg", b"\xff\xd8bytes")

    assert list(tmp_path.iterdir()) == []


JPEG = b"\xff\xd8\xff\xe0jpegbytes"


def a_source(
    tmp_path: Path,
    filenames: dict[int, str],
    responses: dict[str, tuple[int, str, bytes]],
    asked: list[str] | None = None,
) -> BlizzardIcons:
    def fetch(url: str) -> tuple[int, str, bytes]:
        if asked is not None:
            asked.append(url)
        return responses.get(url, (404, "text/html", b""))

    return BlizzardIcons(filenames, IconStore(tmp_path), fetch)


def test_an_ability_the_dictionary_names_is_embedded(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (200, "image/jpeg", JPEG)})
    assert source.data_uri(1) == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()


def test_an_ability_the_dictionary_does_not_name_draws_nothing(tmp_path: Path) -> None:
    assert a_source(tmp_path, {}, {}).data_uri(1) is None


def test_ability_zero_draws_nothing_even_though_it_names_a_file(tmp_path: Path) -> None:
    # The dictionary maps zero to "Unknown Ability" and gives it a real axe icon.
    # Drawing it would put art beside a row nobody identified.
    url = "https://render.worldofwarcraft.com/eu/icons/36/inv_axe_02.jpg"
    source = a_source(tmp_path, {0: "inv_axe_02.jpg"}, {url: (200, "image/jpeg", JPEG)})
    assert source.data_uri(0) is None


def test_a_refusal_carrying_xml_is_a_miss_and_is_never_embedded(tmp_path: Path) -> None:
    # Blizzard answers an absent icon with 403 and an XML body, not a 404.
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (403, "application/xml", b"<Error/>")})
    assert source.data_uri(1) is None


def test_a_200_that_is_not_an_image_is_a_miss(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    source = a_source(tmp_path, {1: "spell_a.jpg"}, {url: (200, "text/html", b"<html>")})
    assert source.data_uri(1) is None


def test_a_non_200_status_with_an_image_content_type_is_still_a_miss(tmp_path: Path) -> None:
    # Both halves of the check must hold: an image content type on a server
    # error is not embedded, just as a 200 with the wrong content type is not.
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    asked: list[str] = []
    responses = {url: (500, "image/jpeg", JPEG)}
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert asked == [url]


def test_a_missing_icon_is_asked_for_once_and_then_remembered(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    asked: list[str] = []
    responses = {url: (403, "application/xml", b"<Error/>")}
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1) is None
    assert asked == [url]


def test_a_stored_icon_is_not_asked_for_again(tmp_path: Path) -> None:
    url = "https://render.worldofwarcraft.com/eu/icons/36/spell_a.jpg"
    asked: list[str] = []
    responses = {url: (200, "image/jpeg", JPEG)}
    a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1)
    a_source(tmp_path, {1: "spell_a.jpg"}, responses, asked).data_uri(1)
    assert asked == [url]


def test_a_name_the_rule_refuses_is_never_requested(tmp_path: Path) -> None:
    asked: list[str] = []
    source = a_source(tmp_path, {1: "../escape.jpg"}, {}, asked)
    assert source.data_uri(1) is None
    assert asked == []

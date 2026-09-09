# ABOUTME: The rules that decide what an icon file name is, and the store that keeps the bytes.
# ABOUTME: No network: every rule here is decided before a request would be made.

from pathlib import Path

from wowperf.adapters.render.icons import IconStore, icon_filename


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

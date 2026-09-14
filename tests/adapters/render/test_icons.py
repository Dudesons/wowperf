# ABOUTME: The rules that decide what an icon file name is, and what address it becomes.
# ABOUTME: No network: every rule here is decided without ever asking the CDN for anything.

from wowperf.adapters.render.icons import CdnIcons, icon_filename


def test_an_ability_the_dictionary_names_is_linked_to_the_cdn() -> None:
    icons = CdnIcons({1: "spell_holy_divineshield.jpg"})
    assert icons.url(1) == (
        "https://wow.zamimg.com/images/wow/icons/medium/spell_holy_divineshield.jpg"
    )


def test_an_ability_the_dictionary_does_not_name_is_linked_to_nothing() -> None:
    assert CdnIcons({}).url(1) is None


def test_ability_zero_is_linked_to_nothing_even_though_it_names_a_file() -> None:
    # The dictionary maps zero to "Unknown Ability" and gives it a real axe icon.
    # Drawing it would put art beside a row nobody identified.
    assert CdnIcons({0: "inv_axe_02.jpg"}).url(0) is None


def test_a_query_suffix_is_stripped_from_the_address() -> None:
    icons = CdnIcons({1: "ability_monk_chiexplosion.jpg?cachebust"})
    assert icons.url(1) == (
        "https://wow.zamimg.com/images/wow/icons/medium/ability_monk_chiexplosion.jpg"
    )


def test_a_name_the_rule_refuses_never_reaches_the_page_as_an_address() -> None:
    # The name arrives from an API and is interpolated into a URL on a page that
    # gets shared, so a name that is not a bare lowercase jpg is refused here
    # rather than trusted to whatever reads it downstream.
    assert CdnIcons({1: "../../evil.jpg"}).url(1) is None
    assert CdnIcons({2: "spell.png"}).url(2) is None
    assert CdnIcons({3: 'a.jpg" onerror="alert(1)'}).url(3) is None


def test_a_plain_icon_name_is_accepted() -> None:
    assert icon_filename("spell_holy_magicalsentry.jpg") == "spell_holy_magicalsentry.jpg"


def test_a_query_suffix_is_stripped_so_two_spellings_name_one_file() -> None:
    assert icon_filename("ability_monk_chiexplosion.jpg?cachebust") == (
        "ability_monk_chiexplosion.jpg"
    )


def test_a_name_that_could_walk_out_of_the_icon_path_is_refused() -> None:
    assert icon_filename("../../../etc/passwd.jpg") is None
    assert icon_filename("sub/dir/spell.jpg") is None


def test_a_name_that_is_not_a_jpg_is_refused() -> None:
    assert icon_filename("spell_holy_magicalsentry.png") is None
    assert icon_filename("") is None


def test_a_name_with_uppercase_letters_is_refused() -> None:
    assert icon_filename("Spell_Holy_MagicalSentry.jpg") is None

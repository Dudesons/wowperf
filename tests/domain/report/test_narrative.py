# ABOUTME: The narrative states no numbers; the report's own sections carry every figure.
# ABOUTME: These pin the tripwire that keeps an unbadged number off the page.

from wowperf.domain.report.narrative import lines_with_digits


def test_an_empty_narrative_has_nothing_to_report() -> None:
    assert lines_with_digits("") == ()


def test_prose_without_a_digit_passes() -> None:
    text = "Your losses are route, not execution. Travel dominates every other figure."
    assert lines_with_digits(text) == ()


def test_a_single_numeral_is_reported_with_its_line_number() -> None:
    assert lines_with_digits("Travel cost 3:13.") == ((1, "Travel cost 3:13."),)


def test_every_offending_line_is_reported_not_only_the_first() -> None:
    text = "Fine.\nTravel cost 3:13.\nAlso fine.\nYou died 4 times."
    assert lines_with_digits(text) == (
        (2, "Travel cost 3:13."),
        (4, "You died 4 times."),
    )


def test_line_numbers_count_blank_lines_so_they_match_an_editor() -> None:
    assert lines_with_digits("Fine.\n\n\nPull 7 was slow.") == ((4, "Pull 7 was slow."),)


def test_a_digit_inside_a_word_still_counts() -> None:
    assert lines_with_digits("The pull7 pack was slow.") == ((1, "The pull7 pack was slow."),)


def test_a_non_ascii_digit_counts() -> None:
    # Arabic-Indic three. `str.isdigit()` is true for it, and it is a number on
    # the page exactly as an ASCII digit would be.
    assert lines_with_digits("Travel cost ٣ minutes.") == ((1, "Travel cost ٣ minutes."),)


def test_a_superscript_digit_counts() -> None:
    assert lines_with_digits("Damage went up².") == ((1, "Damage went up²."),)


def test_spelled_out_quantities_pass_because_this_is_a_tripwire_not_a_proof() -> None:
    # Stated as a test so nobody later mistakes the check for a guarantee: the
    # instruction forbids quantities, this function only catches numerals.
    assert lines_with_digits("You lost three minutes to travel.") == ()

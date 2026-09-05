# ABOUTME: The narrative states no numbers; every figure lives in a section that owns it.
# ABOUTME: A pure check over text, so the command can refuse a narrative before fetching.


def lines_with_digits(text: str) -> tuple[tuple[int, str], ...]:
    """Every line carrying a digit, as (line number, line) pairs, in order.

    The report's own sections carry every figure, badged and sourced, directly
    below the narrative. A number repeated in the narrative is a second,
    unbadged claim competing with the first.

    Line numbers start at 1 and count blank lines, so they match what an editor
    shows. Every offending line is returned rather than only the first, so
    fixing a narrative is not whack-a-mole.

    This is a tripwire, not a proof: it catches numerals, which is where drift
    happens. "You lost three minutes to travel" passes, and the instruction that
    forbids it lives in the `analyzing-a-run` skill.
    """
    return tuple(
        (number, line)
        for number, line in enumerate(text.splitlines(), start=1)
        if any(character.isdigit() for character in line)
    )

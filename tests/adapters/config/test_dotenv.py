# ABOUTME: Behaviour tests for reading the credentials dotfile a new clone is told to create.
# ABOUTME: Each case here is a way a guildmate's own file differs from the example we ship.

from pathlib import Path

from wowperf.adapters.config.dotenv import apply_dotenv, read_dotenv


def test_a_key_and_value_are_read_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("WCL_CLIENT_ID=abc123\n", encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_comments_and_blank_lines_are_skipped(tmp_path: Path) -> None:
    # The file we ship opens with a comment block; without this every one of
    # those lines becomes a key and the real ones are lost in the noise.
    path = tmp_path / ".env"
    path.write_text("# create a client first\n\nWCL_CLIENT_ID=abc123\n", encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_surrounding_quotes_are_stripped_from_the_value(tmp_path: Path) -> None:
    # Quoting is how most dotfiles are written elsewhere. Keeping the quotes
    # sends them to the token endpoint, which answers 401 and says nothing
    # about why.
    path = tmp_path / ".env"
    path.write_text('WCL_CLIENT_SECRET="s3cret"\n', encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_SECRET": "s3cret"}


def test_whitespace_around_the_key_and_value_is_dropped(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("  WCL_CLIENT_ID = abc123  \n", encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_a_utf_16_file_is_decoded(tmp_path: Path) -> None:
    # PowerShell's `>` and Out-File write UTF-16 with a BOM. A UTF-8 reader
    # sees spaced-out mojibake and finds no credentials at all.
    path = tmp_path / ".env"
    path.write_bytes("WCL_CLIENT_ID=abc123\n".encode("utf-16"))
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_a_utf_8_byte_order_mark_is_not_part_of_the_first_key(tmp_path: Path) -> None:
    # Notepad writes this one. The BOM would otherwise glue itself to the
    # first key, so WCL_CLIENT_ID silently becomes a different variable.
    path = tmp_path / ".env"
    path.write_bytes("WCL_CLIENT_ID=abc123\n".encode("utf-8-sig"))
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_a_value_containing_an_equals_sign_survives_intact(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("WCL_CLIENT_SECRET=aa=bb=cc\n", encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_SECRET": "aa=bb=cc"}


def test_a_line_with_no_equals_sign_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("paste your client id below\nWCL_CLIENT_ID=abc123\n", encoding="utf-8")
    assert read_dotenv(path) == {"WCL_CLIENT_ID": "abc123"}


def test_a_missing_file_reads_as_no_values(tmp_path: Path) -> None:
    # Credentials may equally come from the real environment; the absence of
    # the file is not an error.
    assert read_dotenv(tmp_path / ".env") == {}


def test_a_value_the_file_supplies_reaches_the_environment(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("WCL_CLIENT_ID=abc123\n", encoding="utf-8")
    environ: dict[str, str] = {}
    apply_dotenv(path, environ)
    assert environ["WCL_CLIENT_ID"] == "abc123"


def test_the_surrounding_environment_wins_over_the_file(tmp_path: Path) -> None:
    # CI and the end-to-end suite export their own credentials; a stale
    # dotfile left in the clone must not quietly replace them.
    path = tmp_path / ".env"
    path.write_text("WCL_CLIENT_ID=from-the-file\n", encoding="utf-8")
    environ = {"WCL_CLIENT_ID": "from-the-environment"}
    apply_dotenv(path, environ)
    assert environ["WCL_CLIENT_ID"] == "from-the-environment"


def test_an_unfilled_value_is_applied_as_empty(tmp_path: Path) -> None:
    # The example file ships with both values blank. Carrying the blank
    # through is what makes the CLI's "set these two variables" message fire
    # for someone who copied the file and stopped there.
    path = tmp_path / ".env"
    path.write_text("WCL_CLIENT_ID=\n", encoding="utf-8")
    environ: dict[str, str] = {}
    apply_dotenv(path, environ)
    assert environ["WCL_CLIENT_ID"] == ""

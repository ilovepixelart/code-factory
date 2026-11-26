"""The line scanners that stand in for TOML source spans: the previous implementation's scanners,
including their zero for a key they cannot see."""

from code_factory.settings.rules.lines import entry_line, header_line, key_line

TEXT = """# comment
[checks]
command = "a"
 timeout = 3

[agents]
timeout = 9
review = true

[agents.models]
brd = "x"

[[automations]]
name = "a"
every = "day"

[[automations]]
name = "b"
every = "week"
"""


def test_a_key_is_found_under_its_own_table_only() -> None:
    assert key_line(TEXT, "checks", "command") == 3
    assert key_line(TEXT, "checks", "timeout") == 4
    assert key_line(TEXT, "agents", "timeout") == 7
    assert key_line(TEXT, "agents", "review") == 8


def test_a_key_that_is_not_there_or_is_written_dotted_reads_zero() -> None:
    assert key_line(TEXT, "checks", "missing") == 0
    assert key_line(TEXT, "agents", "brd") == 0
    assert key_line(TEXT, "agents.models", "brd") == 11
    assert key_line('[agents]\nmodels.brd = "x"\n', "agents", "models") == 0
    assert key_line('[agents]\nmodels = { brd = "x" }\n', "agents", "brd") == 0
    assert key_line("", "agents", "x") == 0


def test_a_list_entry_is_found_by_its_position() -> None:
    assert entry_line(TEXT, "automations", 0, "name") == 14
    assert entry_line(TEXT, "automations", 0, "every") == 15
    assert entry_line(TEXT, "automations", 1, "name") == 18
    assert entry_line(TEXT, "automations", 1, "every") == 19
    assert entry_line(TEXT, "automations", 2, "name") == 0
    assert entry_line(TEXT, "automations", 0, "title") == 0


def test_a_header_is_found_by_its_position() -> None:
    assert header_line(TEXT, "agents") == 6
    assert header_line(TEXT, "automations", 1) == 17
    assert header_line(TEXT, "automations", 2) == 0
    assert header_line(TEXT, "nothing") == 0

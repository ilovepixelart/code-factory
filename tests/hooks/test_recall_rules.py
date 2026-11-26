"""What recall hands a session within its cap: sizes are hand-worked from the specification."""

from code_factory.hooks.models import RecallParts
from code_factory.hooks.rules.recall import CAP, ticket_lines, title, within

HEADING = "code-factory: read again at the start of this session."
MEMORY_HEADING = "Standing rules, decisions and lessons, each with why:"
LEFT_PREFIX = (
    "Left out over the memory budget of 8,000 characters (read them with the search_memory tool): "
)
INDEX_HEADING = "Archived memory, not loaded: read one with the search_memory tool (id: title):"


def size(line: str) -> int:
    """Characters of a line with its line end."""
    return len(line) + 1


def parts(**given: object) -> RecallParts:
    fields: dict[str, object] = {
        "memory": [],
        "left": [],
        "ticket": [],
        "notices": [],
        "overflow": None,
        "index": [],
    }
    fields.update(given)
    return RecallParts.model_validate(fields)


def test_the_cap_is_ten_thousand_characters() -> None:
    assert CAP == 10_000


def test_the_lines_come_in_order_heading_memory_overflow_left_out_notices_ticket_index() -> None:
    recalled = within(
        parts(
            memory=[("m1", "- Rule one Why: because"), ("m2", "- Rule two")],
            left=[("m3", "- Lesson three Why: later")],
            ticket=["Ticket on this branch: CF-1 Work (stage: build, branch ticket/cf-1)"],
            notices=["note: an entry could not be read"],
            overflow="The rules and decisions above take 5 characters over the memory budget.",
            index=["- m9: Old thing"],
        )
    )

    assert recalled.text == (
        f"{HEADING}\n{MEMORY_HEADING}\n- Rule one Why: because\n- Rule two\n"
        "The rules and decisions above take 5 characters over the memory budget.\n"
        f"{LEFT_PREFIX}Lesson three\n"
        "note: an entry could not be read\n"
        "Ticket on this branch: CF-1 Work (stage: build, branch ticket/cf-1)\n"
        f"{INDEX_HEADING}\n- m9: Old thing\n"
    )
    assert (recalled.memory_kept, recalled.ticket_kept) == (2, 1)


def test_ticket_lines_that_fill_the_room_exactly_stay_and_one_character_over_drops_the_last() -> (
    None
):
    first, second = "t" * 20, "u" * 30
    exact = size(HEADING) + size(first) + size(second)

    kept = within(parts(ticket=[first, second]), cap=exact)
    one_short = within(parts(ticket=[first, second]), cap=exact - 1)

    assert kept.text == f"{HEADING}\n{first}\n{second}\n"
    assert kept.ticket_kept == 2
    assert one_short.text == f"{HEADING}\n{first}\n"
    assert one_short.ticket_kept == 1


def test_a_ticket_line_that_does_not_fit_ends_the_ticket_lines_even_if_a_later_one_would() -> None:
    long, short = "t" * 50, "u"

    recalled = within(parts(ticket=[long, short]), cap=size(HEADING) + size(short))

    assert recalled.text == f"{HEADING}\n"
    assert recalled.ticket_kept == 0


def test_the_left_out_line_names_the_titles_until_one_character_too_many() -> None:
    left = [("a", "- Alpha rule Why: one"), ("b", "- Beta rule Why: two")]
    named = f"{LEFT_PREFIX}Alpha rule; Beta rule"
    exact = size(HEADING) + size(named)

    by_name = within(parts(left=left), cap=exact)
    by_count = within(parts(left=left), cap=exact - 1)

    assert by_name.text == f"{HEADING}\n{named}\n"
    assert by_count.text == f"{HEADING}\n{LEFT_PREFIX}2 entries\n"


def test_a_title_is_the_statement_before_why_cut_to_sixty_characters() -> None:
    assert title("- Use the port Why: tests need it") == "Use the port"
    assert title("- " + "s" * 80 + " Why: x") == "s" * 60
    assert title("- No reason given") == "No reason given"
    assert title("Without the dash") == "Without the dash"


def test_the_memory_heading_is_absent_when_no_memory_line_stays() -> None:
    recalled = within(parts(memory=[("m1", "- " + "x" * 400)]), cap=size(HEADING) + 150)

    assert MEMORY_HEADING not in recalled.text
    assert recalled.memory_kept == 0
    assert recalled.text == f"{HEADING}\n{LEFT_PREFIX}1 entries\n"


def test_memory_lines_stay_in_load_order_while_the_left_out_line_for_the_rest_fits() -> None:
    kept_a, kept_b = "- " + "a" * 30, "- " + "b" * 30
    cut = "- " + "c" * 148
    count_line = f"{LEFT_PREFIX}1 entries"
    cap = size(HEADING) + size(MEMORY_HEADING) + size(kept_a) + size(kept_b) + size(count_line)

    recalled = within(parts(memory=[("a", kept_a), ("b", kept_b), ("c", cut)]), cap=cap)

    assert recalled.text == f"{HEADING}\n{MEMORY_HEADING}\n{kept_a}\n{kept_b}\n{count_line}\n"
    assert recalled.memory_kept == 2
    assert len(recalled.text) == cap


def test_every_memory_line_stays_when_all_fit_and_nothing_is_left_out() -> None:
    lines = ["- " + "a" * 30, "- " + "b" * 30]
    cap = size(HEADING) + size(MEMORY_HEADING) + sum(size(line) for line in lines)

    recalled = within(parts(memory=[("a", lines[0]), ("b", lines[1])]), cap=cap)

    assert recalled.text == f"{HEADING}\n{MEMORY_HEADING}\n{lines[0]}\n{lines[1]}\n"
    assert recalled.memory_kept == 2


def test_the_index_is_all_its_entries_then_a_count_then_nothing() -> None:
    entries = ["- i1: first", "- i2: second", "- i3: " + "z" * 80]
    more = "1 more archived entries: search_memory finds them."
    full = size(HEADING) + size(INDEX_HEADING) + sum(size(e) for e in entries)

    whole = within(parts(index=entries), cap=full)
    trimmed = within(parts(index=entries), cap=full - 1)
    count_only = within(
        parts(index=entries),
        cap=size(HEADING)
        + size(INDEX_HEADING)
        + size("3 more archived entries: search_memory finds them."),
    )
    nothing = within(
        parts(index=entries),
        cap=size(HEADING)
        + size(INDEX_HEADING)
        + size("3 more archived entries: search_memory finds them.")
        - 1,
    )

    assert whole.text == f"{HEADING}\n{INDEX_HEADING}\n{entries[0]}\n{entries[1]}\n{entries[2]}\n"
    assert trimmed.text == f"{HEADING}\n{INDEX_HEADING}\n{entries[0]}\n{entries[1]}\n{more}\n"
    assert count_only.text == (
        f"{HEADING}\n{INDEX_HEADING}\n3 more archived entries: search_memory finds them.\n"
    )
    assert nothing.text == f"{HEADING}\n"


def test_an_empty_index_adds_no_heading() -> None:
    assert within(parts(index=[])).text == f"{HEADING}\n"


def test_four_hundred_requirement_rows_stay_within_the_cap_and_the_left_out_line_comes_third() -> (
    None
):
    rows = [
        f"| CF-1-R{n} | Requirement number {n} reads like a long sentence |" for n in range(1, 401)
    ]
    first = "Ticket on this branch: CF-1 Work (stage: build, branch ticket/cf-1)"
    memory = [(f"m{n}", f"- Rule {n} " + "x" * 1000) for n in range(1, 10)]

    recalled = within(
        parts(
            memory=memory,
            ticket=[first, "Requirements:", *rows],
            overflow="The rules and decisions above take 500 characters over the memory budget.",
        )
    )

    lines = recalled.text.splitlines()
    assert len(recalled.text) <= CAP
    assert lines[0] == HEADING
    assert lines[1].startswith("The rules and decisions above take 500")
    assert lines[2] == f"{LEFT_PREFIX}9 entries"
    assert lines[3] == first
    assert recalled.memory_kept == 0


def test_the_ticket_lines_are_the_ticket_then_its_requirements_then_its_role_rules() -> None:
    lines = ticket_lines(
        "CF-7",
        "Add the thing",
        "build",
        "ticket/cf-7",
        requirements=["| CF-7-R1 | It does the thing |"],
        role_rules=["build rule Run the tests Why: they catch drift"],
    )

    assert lines == [
        "Ticket on this branch: CF-7 Add the thing (stage: build, branch ticket/cf-7)",
        "Requirements:",
        "| CF-7-R1 | It does the thing |",
        "build rule Run the tests Why: they catch drift",
    ]


def test_a_ticket_with_no_requirements_has_no_requirements_heading() -> None:
    assert ticket_lines("CF-7", "T", "spec", "", requirements=[], role_rules=[]) == [
        "Ticket on this branch: CF-7 T (stage: spec, branch )"
    ]

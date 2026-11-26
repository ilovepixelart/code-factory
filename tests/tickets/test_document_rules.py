"""What a document must hold, judged without a database.

The requirements shape is the previous implementation's template: a `## Requirements` table of
`ID | Requirement | Named check`, every row naming its check.
"""

from code_factory.tickets.models import DocumentName, Problem
from code_factory.tickets.rules import validate_document

GOOD = """# CF-7 product requirements

## Requirements

| ID | Requirement | Named check |
|---|---|---|
| CF-7-R1 | When saved, the title is shown | test_the_title_is_shown |
| CF-7-R2 | The page reads well | review |
"""


def test_requirements_with_a_check_on_every_row_pass() -> None:
    assert validate_document(DocumentName.REQUIREMENTS, GOOD) == []


def test_a_requirement_row_without_a_named_check_is_named_with_its_line() -> None:
    text = GOOD.replace("| review |", "|  |")
    assert validate_document(DocumentName.REQUIREMENTS, text) == [
        Problem(line=8, message="requirements row 2 (CF-7-R2) has no named check")
    ]


def test_requirements_without_their_table_are_refused() -> None:
    assert validate_document(DocumentName.REQUIREMENTS, "# Notes\n\nNothing yet.\n") == [
        Problem(line=0, message="requirements has no ## Requirements table")
    ]


def test_a_document_of_another_kind_is_free_text() -> None:
    assert validate_document(DocumentName.NOTES, "anything at all") == []

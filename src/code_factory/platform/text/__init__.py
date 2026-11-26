"""Pure text helpers every module shares: moments, words, JSON layout, markdown, screens."""

from code_factory.platform.text.json_layout import Style, render
from code_factory.platform.text.markdown import INLINE_LIMIT
from code_factory.platform.text.markdown import render as render_markdown
from code_factory.platform.text.markdown_tables import (
    Row,
    line_prefixes,
    mentions,
    section,
    section_rows,
)
from code_factory.platform.text.masking import REDACTED, masked
from code_factory.platform.text.moments import (
    day_minute,
    day_text,
    epoch_day,
    is_iso_date,
    iso_date_days,
    stamp,
    stamp_moment,
)
from code_factory.platform.text.paging import (
    DEFAULT_SIZE,
    MAX_SIZE,
    PAGE_REFUSED,
    SIZE_REFUSED,
    Paged,
    Paging,
    page_of,
)
from code_factory.platform.text.patterns import is_valid_pattern, name_matches
from code_factory.platform.text.screen import Finding, Kind, remote_host
from code_factory.platform.text.screen import secrets as screen_secrets
from code_factory.platform.text.screen import words as screen_words
from code_factory.platform.text.screen_reading import shown
from code_factory.platform.text.source_tests import defined_functions, python_nodes, rust_tests
from code_factory.platform.text.words import one_line, quoted_list, scalar_text, span

__all__ = [
    "DEFAULT_SIZE",
    "INLINE_LIMIT",
    "MAX_SIZE",
    "PAGE_REFUSED",
    "REDACTED",
    "SIZE_REFUSED",
    "Finding",
    "Kind",
    "Paged",
    "Paging",
    "Row",
    "Style",
    "day_minute",
    "day_text",
    "defined_functions",
    "epoch_day",
    "is_iso_date",
    "is_valid_pattern",
    "iso_date_days",
    "line_prefixes",
    "masked",
    "mentions",
    "name_matches",
    "one_line",
    "page_of",
    "python_nodes",
    "quoted_list",
    "remote_host",
    "render",
    "render_markdown",
    "rust_tests",
    "scalar_text",
    "screen_secrets",
    "screen_words",
    "section",
    "section_rows",
    "shown",
    "span",
    "stamp",
    "stamp_moment",
]

from code_factory.platform import text

DOCUMENTED = {
    "DEFAULT_SIZE", "Finding", "INLINE_LIMIT", "Kind", "MAX_SIZE", "PAGE_REFUSED", "Paged",
    "Paging", "REDACTED", "Row", "SIZE_REFUSED", "Style", "day_minute", "day_text",
    "defined_functions", "epoch_day", "is_iso_date", "is_valid_pattern", "iso_date_days",
    "line_prefixes", "masked", "mentions", "name_matches", "one_line", "page_of", "python_nodes",
    "quoted_list", "remote_host", "render", "render_markdown", "rust_tests", "scalar_text",
    "screen_secrets", "screen_words", "section", "section_rows", "shown", "span", "stamp",
    "stamp_moment",
}  # fmt: skip


def test_the_public_names_are_the_documented_ones() -> None:
    assert set(text.__all__) == DOCUMENTED
    assert len(text.__all__) == len(set(text.__all__))


def test_every_public_name_resolves() -> None:
    assert [name for name in text.__all__ if not hasattr(text, name)] == []

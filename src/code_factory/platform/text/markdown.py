"""Markdown to HTML that is safe to show: raw HTML and unsafe links stay text."""

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

# About 1 ms per KiB: a caller renders text longer than this in a worker thread so the event loop
# never waits past 100 ms (docs/async.md).
INLINE_LIMIT = 32_768

# `html=False` shows raw HTML as text; the default link validation keeps `javascript:`,
# `vbscript:`, `file:` and `data:` destinations as text (images only for gif, png, jpeg, webp).
# A task list item is a disabled checkbox: the text is edited as Markdown, never through the box.
_MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable("table").use(tasklists_plugin)


def render(text: str) -> str:
    """The HTML of a markdown text: CommonMark with tables and task lists, no raw HTML."""
    return str(_MARKDOWN.render(text))

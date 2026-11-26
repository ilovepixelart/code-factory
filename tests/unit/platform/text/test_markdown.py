import json
from pathlib import Path

import pytest

from code_factory.platform.text import INLINE_LIMIT, render_markdown
from growth import FACTOR, LINEAR_BOUND, growth

FORMATS = Path(__file__).resolve().parents[3] / "support/golden" / "formats" / "markdown"
CASES = json.loads((FORMATS / "cases.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((FORMATS / "cases.golden.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("text", "html"), list(zip(CASES, GOLDEN, strict=True)))
def test_every_golden_case(text: str, html: str) -> None:
    assert render_markdown(text) == html


def test_plain_markdown_is_commonmark() -> None:
    assert render_markdown("") == ""
    assert render_markdown("hello") == "<p>hello</p>\n"
    assert render_markdown("# Title\n\n*a* **b**") == (
        "<h1>Title</h1>\n<p><em>a</em> <strong>b</strong></p>\n"
    )
    assert render_markdown("- one\n- two") == "<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n"
    assert render_markdown("```\na < b\n```") == "<pre><code>a &lt; b\n</code></pre>\n"


def test_raw_html_shows_as_text() -> None:
    assert render_markdown("<div>x</div>") == "<p>&lt;div&gt;x&lt;/div&gt;</p>\n"
    assert render_markdown("a <b>c</b>") == "<p>a &lt;b&gt;c&lt;/b&gt;</p>\n"


def test_a_link_with_an_allowed_scheme_is_a_link() -> None:
    assert render_markdown("[a](https://x.test)") == '<p><a href="https://x.test">a</a></p>\n'


@pytest.mark.parametrize(
    ("text", "html"),
    [
        ("[a](javascript:x)", "<p>[a](javascript:x)</p>\n"),
        ("[a](JavaScript:x)", "<p>[a](JavaScript:x)</p>\n"),
        ("[a](  javascript:x)", "<p>[a](  javascript:x)</p>\n"),
        ("<vbscript:x>", "<p>&lt;vbscript:x&gt;</p>\n"),
        ("![i](data:text/html,x)", "<p>![i](data:text/html,x)</p>\n"),
    ],
)
def test_a_link_with_a_refused_scheme_stays_text(text: str, html: str) -> None:
    assert render_markdown(text) == html


def test_an_image_data_url_is_allowed_for_png_only_among_these() -> None:
    assert render_markdown("![i](data:image/png;base64,AA)") == (
        '<p><img src="data:image/png;base64,AA" alt="i" /></p>\n'
    )
    assert render_markdown("![i](data:image/svg+xml;base64,AA)") == (
        "<p>![i](data:image/svg+xml;base64,AA)</p>\n"
    )


def test_a_definition_with_a_refused_scheme_stays_text_outside_a_fence() -> None:
    assert render_markdown("[x]: javascript:y\n\n[x]") == "<p>[x]: javascript:y</p>\n<p>[x]</p>\n"
    assert render_markdown("```\n[x]: javascript:y\n```") == (
        "<pre><code>[x]: javascript:y\n</code></pre>\n"
    )


def test_a_table_alignment_is_a_style() -> None:
    table = "| a | b | c |\n|:-|:-:|-:|\n| 1 | 2 | 3 |"
    assert render_markdown(table) == (
        "<table>\n<thead>\n<tr>\n"
        '<th style="text-align:left">a</th>\n<th style="text-align:center">b</th>\n'
        '<th style="text-align:right">c</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n'
        '<td style="text-align:left">1</td>\n<td style="text-align:center">2</td>\n'
        '<td style="text-align:right">3</td>\n</tr>\n</tbody>\n</table>\n'
    )


def test_rendering_grows_linearly_up_to_the_inline_limit() -> None:
    paragraph = "A *line* with `code`, a [link](https://example.com) and **bold** words.\n\n"

    def render(size: int) -> None:
        render_markdown((paragraph * (size // len(paragraph) + 1))[:size])

    assert growth(render, INLINE_LIMIT // FACTOR) < LINEAR_BOUND


def test_a_task_list_renders_as_disabled_checkboxes() -> None:
    assert render_markdown("- [ ] open\n- [x] done") == (
        '<ul class="contains-task-list">\n'
        '<li class="task-list-item"><input class="task-list-item-checkbox" disabled="disabled"'
        ' type="checkbox"> open</li>\n'
        '<li class="task-list-item"><input class="task-list-item-checkbox" checked="checked"'
        ' disabled="disabled" type="checkbox"> done</li>\n'
        "</ul>\n"
    )


def test_brackets_that_are_not_a_task_stay_text() -> None:
    assert render_markdown("- [y] no\n\n[ ] alone") == (
        "<ul>\n<li>[y] no</li>\n</ul>\n<p>[ ] alone</p>\n"
    )

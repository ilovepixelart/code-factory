"""Task set files: names, parsing, quoting and the text appended to a set."""

import tomllib

import pytest

from code_factory.evals.models import Stage
from code_factory.evals.rules import (
    BUILD_HEADER,
    append_text,
    escape_block,
    parse_task_set,
    set_name_ok,
    task_block,
    toml_string,
)
from code_factory.platform.errors import BadRequestError

BUILD = '[[task]]\nid = "t1"\nbase = "abc"\nprompt = "do it"\ncheck = "pytest"\n'


@pytest.mark.parametrize("name", ["smoke", "a", "v1.2", "a_b-c", "0x", "A.b"])
def test_a_plain_segment_is_a_set_name(name: str) -> None:
    assert set_name_ok(name)


@pytest.mark.parametrize("name", ["", "../x", "a/b", ".hidden", "-a", "a b", "..", "a\n"])
def test_a_path_or_odd_segment_is_not_a_set_name(name: str) -> None:
    assert not set_name_ok(name)


def test_a_set_without_a_stage_is_a_build_set() -> None:
    parsed = parse_task_set(BUILD)
    assert parsed.stage is Stage.BUILD
    assert [t.id for t in parsed.tasks] == ["t1"]
    assert parsed.tasks[0].check == "pytest"


@pytest.mark.parametrize("stage", ["spec", "build", "review"])
def test_the_three_stages_are_read(stage: str) -> None:
    assert parse_task_set(f'stage = "{stage}"\n').stage.value == stage


def test_another_stage_is_refused_with_its_sentence() -> None:
    with pytest.raises(BadRequestError) as caught:
        parse_task_set('stage = "deploy"\n')
    assert str(caught.value) == "the set's stage deploy is not spec, build or review"


def test_a_task_names_every_field_it_lacks() -> None:
    with pytest.raises(BadRequestError) as caught:
        parse_task_set('[[task]]\nid = "t1"\nbase = ""\nprompt = "p"\n')
    assert str(caught.value) == "task t1 has no base, check"


def test_a_task_without_an_id_is_named_by_a_question_mark() -> None:
    with pytest.raises(BadRequestError) as caught:
        parse_task_set('[[task]]\nbase = "b"\nprompt = "p"\ncheck = "c"\n')
    assert str(caught.value) == "task ? has no id"


def test_a_review_without_its_change_is_refused() -> None:
    with pytest.raises(BadRequestError) as caught:
        parse_task_set('[[review]]\nid = "r"\nticket = "CF-1"\nbase = "a"\n')
    assert str(caught.value) == "task r has no head"


def test_a_review_with_files_is_an_escape_and_without_is_clean() -> None:
    text = (
        '[[review]]\nid = "e"\nticket = "CF-1"\nbase = "a"\nhead = "b"\nfiles = []\n'
        '[[review]]\nid = "c"\nticket = "CF-2"\nbase = "a"\nhead = "b"\n'
    )
    escape, clean = parse_task_set(text).reviews
    assert escape.files == ()
    assert clean.files is None


def test_a_review_ticket_outside_the_id_characters_is_refused() -> None:
    text = '[[review]]\nid = "r"\nticket = "CF 1"\nbase = "a"\nhead = "b"\n'
    with pytest.raises(BadRequestError) as caught:
        parse_task_set(text)
    assert str(caught.value) == "task r: CF 1 is not a ticket id"


def test_text_that_is_not_toml_is_refused() -> None:
    with pytest.raises(BadRequestError, match="is not TOML"):
        parse_task_set("[[task")


@pytest.mark.parametrize(
    "value", ['a"b', "back\\slash", "new\nline", "tab\t", "del\x7f", "\u2028", "astral \U0001f600"]
)
def test_a_quoted_string_reads_back_as_it_was(value: str) -> None:
    assert tomllib.loads("k = " + toml_string(value))["k"] == value


def test_task_block_has_the_exact_text() -> None:
    assert task_block("t1", "abc", "do it", "pytest") == BUILD


def test_escape_block_has_the_exact_text_and_sorted_files() -> None:
    assert escape_block("CF-9", "CF-4", "b1", "h1", ["z.py", "a.py"]) == (
        '[[review]]\nid = "escape-CF-9"\nticket = "CF-4"\nbase = "b1"\nhead = "h1"\n'
        'defect = "CF-9"\nfiles = ["a.py", "z.py"]\n'
    )


def test_an_empty_file_gets_the_header_for_a_build_task_only() -> None:
    assert append_text("", BUILD, BUILD_HEADER) == 'stage = "build"\n\n' + BUILD
    assert append_text("", "[[review]]\n", "") == "[[review]]\n"


def test_the_separator_follows_the_end_of_the_existing_text() -> None:
    assert append_text("a = 1\n", BUILD, BUILD_HEADER) == "\n" + BUILD
    assert append_text("a = 1", BUILD, BUILD_HEADER) == "\n\n" + BUILD

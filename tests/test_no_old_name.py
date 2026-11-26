import re

import pytest

from repo_files import VENDORED, repo_files, text_lines

# Built from parts so this file does not match itself.
_NAME = "whole" + "cycle"
_ABBREVIATION = "W" + "C"
_NAME_PATTERN = re.compile(rf"{_NAME}|whole[-_ ]cycle", re.IGNORECASE)
# Whole word or ticket-id prefix, so `wcwidth`, `swc` and `wc -l` stay legal.
_ABBREVIATION_PATTERN = re.compile(rf"\b{_ABBREVIATION}\b|\b{_ABBREVIATION.lower()}-")


def mentions_old_name(text: str, *, abbreviation: bool = True) -> bool:
    """Whether `text` names the previous implementation or, optionally, its ticket prefix."""
    return bool(_NAME_PATTERN.search(text) or (abbreviation and _ABBREVIATION_PATTERN.search(text)))


@pytest.mark.parametrize(
    "text",
    [
        f"see the {_NAME.title()} board",
        f"the {_NAME.upper()}_ variable",
        f"a {_NAME[:5]}-{_NAME[5:]} spelling",
        f"ticket {_ABBREVIATION}-12",
        f"branch ticket/{_ABBREVIATION.lower()}-12",
        f"the {_ABBREVIATION} board",
        f".{_NAME}/tickets",
    ],
)
def test_the_old_name_and_ticket_prefix_are_found(text: str) -> None:
    assert mentions_old_name(text)


@pytest.mark.parametrize(
    "text",
    [
        "from wcwidth import wcswidth",
        "swc is a compiler",
        "install swc-loader",
        "the TWC channel and NWCX",
        "run wc -l on the file",
        "ticket CF-12 on branch ticket/cf-12",
    ],
)
def test_ordinary_words_that_contain_the_letters_pass(text: str) -> None:
    assert not mentions_old_name(text)


def test_the_previous_name_appears_in_no_path_and_no_content() -> None:
    found = []
    for path in repo_files(include_vendored=True):
        if mentions_old_name(str(path)):
            found.append(f"{path}: in the file name")
        # Minified third-party code has short identifiers that look like the abbreviation.
        abbreviation = not str(path).startswith(VENDORED)
        found.extend(
            f"{path}:{number}: {line.strip()[:80]}"
            for number, line in enumerate(text_lines(path), start=1)
            if mentions_old_name(line, abbreviation=abbreviation)
        )
    assert not found, "the previous implementation is not named in this repository:\n" + "\n".join(
        found
    )

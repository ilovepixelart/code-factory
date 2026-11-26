"""The name and root of a tracked repository, worked by hand from the previous implementation.

A repository is addressed by its folder name in every URL; the root is an absolute path.
"""

from pathlib import PurePosixPath

import pytest

from code_factory.platform.errors import BadRequestError
from code_factory.repositories.rules import checked_root, name_of


def test_the_name_is_the_folder_name() -> None:
    assert name_of(PurePosixPath("/Users/alex/code/sample")) == "sample"


def test_a_trailing_separator_does_not_change_the_root() -> None:
    assert checked_root(PurePosixPath("/srv/code/sample/")) == PurePosixPath("/srv/code/sample")


def test_dot_segments_are_collapsed_in_the_root() -> None:
    assert checked_root(PurePosixPath("/srv/code/other/../sample")) == PurePosixPath(
        "/srv/code/sample"
    )


def test_a_relative_path_is_refused_with_the_path() -> None:
    with pytest.raises(BadRequestError, match="code/sample is not an absolute path"):
        checked_root(PurePosixPath("code/sample"))


def test_the_filesystem_root_has_no_name_and_is_refused() -> None:
    with pytest.raises(BadRequestError, match="/ has no folder name to track under"):
        checked_root(PurePosixPath("/"))


def test_a_double_leading_slash_names_the_same_root() -> None:
    assert checked_root(PurePosixPath("//srv/code/sample")) == PurePosixPath("/srv/code/sample")

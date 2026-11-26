"""The delivery service over a real database, with a scripted gh and fake neighbours."""

import pytest

from code_factory.delivery.adapters.gh import ForbiddenCallError, guard
from delivery_fakes import (
    TIP,
    URL,
)


def test_gh_refuses_every_merge_shape_but_the_one() -> None:
    guard(["pr", "merge", URL, "--merge", "--match-head-commit", TIP])
    for argv in (
        ["pr", "merge", URL, "--admin"],
        ["pr", "merge", URL, "--squash", "--match-head-commit", TIP],
        ["pr", "merge", URL, "--merge"],
        ["pr", "merge", "--repo", "--merge", "--match-head-commit", TIP],
    ):
        with pytest.raises(ForbiddenCallError):
            guard(argv)

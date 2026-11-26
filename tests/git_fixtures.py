"""Fixtures of the git tests: a checkout with an origin, the fakes and a service over them."""

from pathlib import Path

import pytest

from code_factory.git.service import GitService
from code_factory.platform.db import UnitOfWork
from git_support import Fakes, make_repo, make_service, ticket_ref


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The main checkout of repository `sample`."""
    return make_repo(tmp_path)


@pytest.fixture
def fakes(root: Path) -> Fakes:
    """The ports: `sample` tracked at `root`, ticket CF-1 without a branch."""
    return Fakes(roots={"sample": root}, tickets={"CF-1": ticket_ref()})


@pytest.fixture
def service(uow: UnitOfWork, fakes: Fakes) -> GitService:
    """The git service over the isolated database connection."""
    return make_service(uow, fakes)

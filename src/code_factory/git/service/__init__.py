"""The git module's public API."""

from code_factory.git.ports import HooksPort
from code_factory.git.service.base import GitPorts
from code_factory.git.service.landing import LandingMixin


class GitService(LandingMixin):
    """Everything git: facts, diffs, trees, run clones, saving and landing, with the runner."""


__all__ = ["GitPorts", "GitService", "HooksPort"]

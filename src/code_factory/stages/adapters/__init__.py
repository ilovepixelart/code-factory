"""IO at the edge of the stages module: git and the test files of a worktree."""

from code_factory.stages.adapters.facts import GitServiceFacts
from code_factory.stages.adapters.files import TestFiles, TestSources, config_has_content
from code_factory.stages.adapters.git import GitDiffReader, GitRunner

__all__ = [
    "GitDiffReader",
    "GitRunner",
    "GitServiceFacts",
    "TestFiles",
    "TestSources",
    "config_has_content",
]

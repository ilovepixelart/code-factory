"""A ticket's git facts, worked out from the facts git read of its whole repository.

The reads and their parsing belong to the git module (`GitService.facts`); this file only answers
for one ticket's branch.
"""

from collections.abc import Collection

from code_factory.git.models import MERGE_LOG_LIMIT, GitFacts
from code_factory.platform.text import line_prefixes
from code_factory.stages.models import BranchFacts


def _branch_tips(branch: str, git: GitFacts) -> list[str]:
    tips = (git.tips.get(branch, ""), git.tips.get(f"origin/{branch}", ""))
    return [tip for tip in tips if tip != ""]


def _branch_merged(branch: str, git: GitFacts) -> bool | None:
    """Whether a tip of `branch` is merged; `None` while it has no tip or the facts are unknown."""
    tips = _branch_tips(branch, git)
    if not git.known or not tips:
        return None
    return any(tip in git.merged_in for tip in tips)


def _is_merged(ticket_id: str, branch: str, git: GitFacts) -> bool:
    if not branch or not git.known:
        return False
    merged = _branch_merged(branch, git)
    if merged is True:
        return True
    if merged is False:
        tips = _branch_tips(branch, git)
        # A fast-forward has no merge commit. Require the ticket's own subject on a tip so
        # a branch just cut from main does not read as merged.
        return (
            branch != git.default_branch
            and all(tip in git.main_line for tip in tips)
            and any(line_prefixes(git.main_subjects.get(tip, ""), ticket_id) for tip in tips)
        )
    return branch in git.merged_heads or line_prefixes(git.log, ticket_id)


def _untraced(ticket_id: str, branch: str, git: GitFacts) -> str:
    traced = not git.known or _branch_merged(branch, git) is not None
    if not branch or traced or _is_merged(ticket_id, branch, git):
        return ""
    return (
        f"{branch} has no local or remote branch here, and {git.default_branch} holds no pull "
        f"request merge of it nor, in its last {MERGE_LOG_LIMIT} commits, a commit starting with "
        f"{ticket_id} that landed work"
    )


def _holds_own_commit(branch: str, git: GitFacts) -> bool:
    return any(
        tip not in git.main_line and tip not in git.merged_in for tip in _branch_tips(branch, git)
    )


def branch_facts(
    ticket_id: str, branch: str, git: GitFacts, *, worktrees: Collection[str]
) -> BranchFacts:
    """The facts of one ticket's branch; `worktrees` are the branches a board tree works on."""
    tips = _branch_tips(branch, git) if branch else []
    return BranchFacts(
        known=git.known,
        local=bool(branch) and branch in git.local,
        pushed=bool(branch) and branch in git.remote,
        in_worktree=bool(branch) and branch in worktrees,
        merged=_is_merged(ticket_id, branch, git),
        has_commits=bool(branch) and _holds_own_commit(branch, git),
        untraced=_untraced(ticket_id, branch, git),
        default_branch=git.default_branch,
        head=tips[0] if tips else "",
    )

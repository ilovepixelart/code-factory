"""The checklist of every stage's evidence for a ticket, worked out from stored facts."""

from code_factory.stages.models import BranchFacts, EvidenceItem


# An absent item's detail completes "needs ...": the board shows it as what holds the ticket.
def _review_detail(branch: str, pushed: bool, opened: str | None, present: bool) -> str:
    if opened is not None and opened != "":
        return opened
    if not branch:
        return "no branch declared"
    if present:
        return f"origin/{branch}"
    if pushed:
        return f"a pull request for {branch}"
    return f"a push of {branch} and a pull request"


def derive_evidence(
    branch: str, facts: BranchFacts, opened: str | None, release: str | None
) -> list[EvidenceItem]:
    """The five items in order spec, build, review, merged, released.

    `opened` is the address of the recorded pull request (`""` when it has none), `None` without
    one; `release` is the name of the release that names the ticket, `None` without one.
    """
    pushed = bool(branch) and facts.pushed
    started = bool(branch) and (facts.local or pushed or facts.in_worktree)
    in_review = pushed and opened is not None
    committed = started and facts.has_commits
    reviewed = facts.merged or in_review
    merged_into = facts.default_branch if facts.merged else f"a merge into {facts.default_branch}"
    return [
        EvidenceItem(
            stage="spec", required=True, present=facts.merged or started, detail="a branch"
        ),
        EvidenceItem(
            stage="build",
            required=True,
            present=facts.merged or in_review or committed,
            detail=f"a commit on {branch}" if branch else "a branch",
        ),
        EvidenceItem(
            stage="review",
            required=True,
            present=reviewed,
            detail=_review_detail(branch, pushed, opened, reviewed),
        ),
        EvidenceItem(
            stage="merged",
            required=True,
            present=facts.merged,
            detail=facts.untraced or merged_into,
        ),
        EvidenceItem(
            stage="released",
            required=False,
            present=release is not None,
            detail=release or "a release note naming it",
        ),
    ]

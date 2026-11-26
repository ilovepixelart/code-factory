"""The one rule of the board merge: every guard on the same head, first failing guard wins."""

from datetime import datetime

from code_factory.delivery.models import MergeFacts, MergeVerdict
from code_factory.delivery.rules.retry import settled

NOT_READY = "its pull request is not open and green"
NOT_DEFAULT_BASE = "its pull request does not merge into the default branch"
HEAD_MOVED = "the pull request's head moved past the commit the board shipped"
NO_SHIPPED = "the commit the board shipped is not recorded, so the merge cannot name it"


def _no(reason: str, *, base_unread: bool = False) -> MergeVerdict:
    return MergeVerdict(ready=False, reason=reason, record_base_unread=base_unread)


def _recorded(facts: MergeFacts) -> MergeVerdict | None:  # noqa: PLR0911  # one return per guard
    pull = facts.pull
    if pull is None or pull.state != "open" or pull.draft or pull.ci not in {"passed", "none"}:
        return _no(NOT_READY)
    if pull.base and pull.base != facts.default_branch:
        return _no(NOT_DEFAULT_BASE)
    if facts.checks_configured and facts.checked != "passed":
        if facts.checked == "failed":
            return _no(f"the board's checks failed on {pull.head}")
        return _no(f"waits for the board's checks on {pull.head}")
    if not pull.shipped_head:
        return _no(NO_SHIPPED)
    if pull.head != pull.shipped_head:
        return _no(HEAD_MOVED)
    if settled(facts.events, pull.url, pull.shipped_head):
        return _no(NOT_READY)
    return None


def _live(facts: MergeFacts) -> MergeVerdict | None:  # noqa: PLR0911  # one return per guard
    live, pull, default = facts.live, facts.pull, facts.default_branch
    if live is None or pull is None:
        return _no(NOT_READY)
    if live.base_error:
        msg = (
            "the base of the pull request could not be read, so it is not merged:"
            f" {live.base_error}"
        )
        return _no(msg, base_unread=True)
    if live.base != default:
        return _no(
            f"the pull request merges into {live.base}, not into {default}: the board merges only"
            f" into {default}"
        )
    if live.head != pull.shipped_head:
        return _no(HEAD_MOVED)
    if live.state.lower() != "open" or live.draft:
        return _no(NOT_READY)
    if live.merge_state != "CLEAN":
        return _no(f"GitHub does not call it mergeable yet: {live.merge_state or 'UNKNOWN'}")
    return None


def merge_decision(facts: MergeFacts) -> MergeVerdict:
    """Ready with the exact merge argv, or the first failing guard's sentence."""
    refused = _recorded(facts) or _live(facts)
    if refused is not None:
        return refused
    pull = facts.pull
    assert pull is not None  # noqa: S101  # _recorded refused a missing pull
    argv = ("pr", "merge", pull.url, "--merge", "--match-head-commit", pull.shipped_head)
    return MergeVerdict(ready=True, argv=argv)


def merge_due(facts: MergeFacts, now: datetime) -> bool:
    """Whether a transient merge failure of the shipped head has waited its time."""
    pull = facts.pull
    if pull is None:
        return False
    for event in facts.events:
        if (
            event.kind == "merge_failed"
            and event.head == pull.shipped_head
            and event.retry_at is not None
            and event.retry_at > now
        ):
            return False
    return True

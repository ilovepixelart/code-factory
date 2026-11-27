"""Identify repairs on the current branch head from settled checks and open pull requests."""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet

from code_factory.checks.service import CheckService
from code_factory.delivery.models import PullView
from code_factory.delivery.service import DeliveryService
from code_factory.platform.services import Services
from code_factory.runs.models import Repair
from code_factory.stages.models import StageAssessment


def repair_for(head: str, pull: PullView | None, *, check_failed: bool) -> Repair | None:
    """Prefer a known merge conflict, then failed checks on the same head."""
    if pull is not None and (pull.state != "open" or pull.head != head):
        pull = None
    if pull is not None and pull.conflict:
        return Repair(
            head=head,
            reason="conflict",
            task="Resolve the merge conflict with the pull request base. Commit the resolution.",
        )
    if check_failed or (pull is not None and (pull.other_ci or pull.ci) == "failed"):
        return Repair(
            head=head,
            reason="ci",
            task="Read the failing CI checks for this branch head, fix the cause, and commit it.",
        )
    return None


async def repairs_for(
    services: Services, assessed: Mapping[str, StageAssessment], running: AbstractSet[str]
) -> dict[str, Repair]:
    """Read check and pull evidence in batches for idle tickets that already have commits."""
    heads = {
        ticket: facts.head
        for ticket, facts in assessed.items()
        if facts.head and facts.stage in {"build", "review"} and ticket not in running
    }
    if not heads:
        return {}
    ids = list(heads)
    checks = services.get(CheckService)
    active = await checks.running(ids)
    failed = await checks.repair_failures(heads)
    pulls = await services.get(DeliveryService).pulls(ids)
    return {
        ticket: repair
        for ticket, head in heads.items()
        if ticket not in active
        and (repair := repair_for(head, pulls.get(ticket), check_failed=ticket in failed))
        is not None
    }

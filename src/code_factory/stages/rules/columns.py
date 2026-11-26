"""Stage names, the column a checklist puts a ticket in, and why a move is refused."""

from collections.abc import Sequence

from code_factory.stages.models import LANDED, RELEASED, EvidenceItem, Stage

NAMES = tuple(stage.value for stage in Stage)
DECLARED = (*NAMES, RELEASED)
_WORK = NAMES[:2]
_LABELS = {name: name.capitalize() for name in NAMES}


def stage_label(name: str) -> str:
    """The name a stage has on the board; `Released` for `released` and for any unknown name."""
    return _LABELS.get(name, "Released")


def stage_index(name: str) -> int | None:
    """A stage's place in process order; `None` for any other name."""
    return NAMES.index(name) if name in NAMES else None


def board_index(name: str) -> int:
    """A name's sort place on the board: its stage's place, an unknown name after every stage."""
    found = stage_index(name)
    return len(NAMES) if found is None else found


def is_done(name: str) -> bool:
    """Whether a stage means the work is done: Review or later, and `released`."""
    found = stage_index(name)
    return name == RELEASED or (found is not None and found >= NAMES.index(Stage.REVIEW.value))


def is_landed(name: str) -> bool:
    """Whether a stage name is Merged or `released`: the work is on main."""
    return name in LANDED


def _item(checklist: Sequence[EvidenceItem], stage: str) -> EvidenceItem | None:
    return next((item for item in checklist if item.stage == stage), None)


def stage_of(checklist: Sequence[EvidenceItem]) -> str:
    """The stage a checklist puts a ticket in; the terminal stages outrank the chain."""
    for stage in (RELEASED, Stage.MERGED.value, Stage.REVIEW.value):
        found = _item(checklist, stage)
        if found is not None and found.present:
            return stage
    for stage in _WORK:
        found = _item(checklist, stage)
        if found is not None and found.required and not found.present:
            return stage
    return Stage.BUILD.value


def effective_stage(declared: str, derived: str) -> str:
    """The stage a hand-declared column names, else the derived one."""
    return declared or derived


def work_done(checklist: Sequence[EvidenceItem]) -> bool:
    """Whether the spec and build items are each present or not required."""
    return all(
        (found := _item(checklist, stage)) is not None and (found.present or not found.required)
        for stage in _WORK
    )


def reviewable(checklist: Sequence[EvidenceItem], current: str) -> bool:
    """Whether a reviewer may look at the work: it is done and not yet in Review."""
    return work_done(checklist) and not is_done(current)


def hold(checklist: Sequence[EvidenceItem]) -> EvidenceItem | None:
    """What holds a ticket in its column: the first required item that is absent."""
    return next((item for item in checklist if item.required and not item.present), None)


def hold_line(checklist: Sequence[EvidenceItem]) -> str:
    """The hold as the card reads it, `needs <stage>: <detail>`; empty when nothing holds."""
    held = hold(checklist)
    return "" if held is None else f"needs {held.stage}: {held.detail}"


def card_hold(checklist: Sequence[EvidenceItem], stage: str) -> dict[str, str] | None:
    """The card's hold object; `None` for a landed stage or when nothing holds."""
    held = None if is_landed(stage) else hold(checklist)
    if held is None:
        return None
    return {"stage": held.stage, "detail": held.detail, "summary": held.detail}


def move_refusal(
    ticket_id: str, current: str, checklist: Sequence[EvidenceItem], target: str
) -> str:
    """Why a card in `current` may not move to `target`; empty when it may."""
    to, start = stage_index(target), stage_index(current)
    if to is None or start is None or to <= start:
        return ""
    following = next(
        (
            stage
            for stage in NAMES[start + 1 :]
            if (found := _item(checklist, stage)) is None or found.required
        ),
        None,
    )
    if following is None:
        return ""
    if target != following:
        return f"{ticket_id} moves one column at a time: {stage_label(following)} is next"
    reached = stage_of(checklist)
    reached_index = stage_index(reached)
    if reached_index is None or reached_index >= to:
        return ""
    found = _item(checklist, reached)
    if found is not None and found.present and target == Stage.REVIEW.value:
        review = _item(checklist, target)
        why = "" if review is None else review.detail
        return f"{ticket_id} needs {why} before {stage_label(target)}"
    detail = "" if found is None else found.detail
    hint = f": start an agent on it, or run code-factory start {ticket_id}"
    needs = f"{ticket_id} needs {detail} before {stage_label(target)}"
    return needs + (hint if detail == "a branch" else "")


def refusals(ticket_id: str, current: str, checklist: Sequence[EvidenceItem]) -> dict[str, str]:
    """One refusal sentence per stage name, empty where the move is allowed."""
    return {stage: move_refusal(ticket_id, current, checklist, stage) for stage in NAMES}


def declared_for_move(declared: str, derived: str, target: str) -> str:
    """The stage to declare for a move to `target`; empty clears the pin.

    A drop on the column the evidence already puts the card in, with nothing declared, only
    reorders: declaring it would pin the card and stop it following its evidence.
    """
    return "" if not declared and target == derived else target

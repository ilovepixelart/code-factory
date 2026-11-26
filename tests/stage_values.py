"""Values the stages tests share: a frozen clock and compact readings of a checklist."""

from datetime import UTC, datetime

from code_factory.stages.models import EvidenceItem

NOW = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)


def shape(items: list[EvidenceItem]) -> str:
    """Each item as `P` or `-` (present) then `r` or `o` (required or optional)."""
    return "".join(
        ("P" if item.present else "-") + ("r" if item.required else "o") for item in items
    )


def details(items: list[EvidenceItem]) -> list[str]:
    return [item.detail for item in items]


def checklist(
    *, spec: bool = False, build: bool = False, review: bool = False, merged: bool = False
) -> list[EvidenceItem]:
    """A checklist worked by hand, each detail named after its stage."""
    present = {"spec": spec, "build": build, "review": review, "merged": merged}
    items = [
        EvidenceItem(stage=s, required=True, present=p, detail=f"{s} item")
        for s, p in present.items()
    ]
    return [*items, EvidenceItem(stage="released", required=False, present=False, detail="notes")]

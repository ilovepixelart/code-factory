"""The Memory page, consolidation suggestions and the owner's changes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from code_factory.board.service import BoardService
from code_factory.memory.models import (
    EntryImage,
    MemoryEdit,
    MemoryEntry,
    MemoryFilter,
    MemoryKind,
    NewMemory,
)
from code_factory.memory.service import MemoryService
from code_factory.memory_extras.models import UNDO_KIND, Restore
from code_factory.memory_extras.service import MemoryExtrasService
from code_factory.platform.web.dependencies import service_of
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService

router = APIRouter(prefix="/api", tags=["memory"])

MemoryDep = Annotated[MemoryService, Depends(service_of(MemoryService))]
ExtrasDep = Annotated[MemoryExtrasService, Depends(service_of(MemoryExtrasService))]
UndoDep = Annotated[UndoService, Depends(service_of(UndoService))]
BoardDep = Annotated[BoardService, Depends(service_of(BoardService))]

OWNER = "owner:owner"
CEILING = 8000  # characters every session may load; the budget cut itself is not built yet
EVERY_SESSION = ("", "core")
PAGE_MAX = 100


def _recall_chars(entry: MemoryEntry) -> int:
    return len(f"- {entry.statement}\n")


def _record(entry: MemoryEntry) -> dict[str, Any]:
    every = entry.scope in EVERY_SESSION
    return {
        "id": entry.id,
        "kind": entry.kind,
        "date": entry.date.isoformat(),
        "source": entry.source,
        "statement": entry.statement,
        "why": entry.why,
        "guard": entry.guard,
        "repository": entry.repository,
        "reviewed": entry.reviewed,
        "guard_state": "",
        "loaded": True,
        "left_out": False,
        "superseded_by": "",
        "scope": entry.scope,
        "supersedes": ", ".join(entry.supersedes),
        "loads": "every session" if every else entry.scope,
        "chars": _recall_chars(entry),
        "proposed": entry.proposed,
        "stale": entry.stale,
        "incomplete": entry.incomplete,
        "review_due": entry.review_due,
        "filing": "committed",
        "received_by": [],
        "cites": ", ".join(entry.cites),
        "stale_cites": [],
    }


def _retired(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "repository": entry.repository,
        "id": entry.id,
        "kind": entry.kind,
        "date": entry.date.isoformat(),
        "source": entry.source,
        "statement": entry.statement,
        "why": entry.why,
        "guard": entry.guard,
        "retired": entry.retired,
        "merged_into": entry.merged_into,
    }


def _found(entry: MemoryEntry) -> dict[str, str]:
    return {
        "repository": entry.repository,
        "path": f"memory/{entry.id}",
        "snippet": entry.statement,
        "open": f"#{entry.id}",
    }


def _window(total: int, page: int, size: int) -> slice:
    last = max((total + size - 1) // size, 1)
    start = (min(max(page, 1), last) - 1) * size
    return slice(start, start + size)


@router.get("/memory", summary="The Memory page")
async def page(  # noqa: PLR0913, PLR0917  # three services and search pagination
    memory: MemoryDep,
    board: BoardDep,
    extras: ExtrasDep,
    q: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 25,
) -> JSONResponse:
    """Entries by where they load, the history, and search results for `q`."""
    active = await memory.list(MemoryFilter())
    proposed = await memory.list(MemoryFilter(status="proposed"))
    retired = await memory.list(MemoryFilter(status="retired"))
    unreviewed = [*proposed, *(e for e in active if not e.reviewed)]
    reviewed = [e for e in active if e.reviewed]
    repositories = sorted(
        {*await board.repositories(), *(e.repository for e in [*active, *proposed, *retired])}
    )
    found = await memory.search(q, MemoryFilter()) if q.strip() else []
    window = _window(len(found), page, size)
    shown = int(window.start // size) + 1
    pairs, proposals = await extras.suggestions_for(active)
    return JSONResponse(
        {
            "repositories": repositories,
            "proposals": [p.model_dump(mode="json") for p in proposals],
            "unreviewed": [_record(e) for e in unreviewed],
            "rules": [_record(e) for e in reviewed if e.kind == "rule"],
            "decisions": [_record(e) for e in reviewed if e.kind == "decision"],
            "lessons": [_record(e) for e in reviewed if e.kind == "lesson"],
            "retired": [_retired(e) for e in retired],
            "loaded_chars": sum(_recall_chars(e) for e in active if e.scope in EVERY_SESSION),
            "ceiling": CEILING,
            "left_out": [],
            "pairs": [p.model_dump(mode="json") for p in pairs],
            "review_queue": [_record(e) for e in active if e.stale],
            "results": [_found(e) for e in found[window]],
            "matched": len(found),
            "page": shown,
            "size": size,
        }
    )


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Texts(_Strict):
    why: str = ""
    source: str = ""
    guard: str = ""
    scope: str = ""


class EditBody(_Texts):
    """The fields to change; `{}` marks the entry reviewed and changes nothing else."""

    kind: MemoryKind | None = None
    statement: str | None = None


class AddBody(_Texts):
    """A new entry; `supersedes` and `cites` are entry ids separated by commas."""

    repository: str
    kind: MemoryKind
    statement: str
    supersedes: str = ""
    cites: str = ""
    expires: str = ""
    until: str = ""


class MergeBody(_Strict):
    """`into`: the id of the entry that keeps it."""

    into: str


class RetireBody(_Strict):
    """`reason`: one line saying why it no longer applies."""

    reason: str


class SupersedeBody(_Strict):
    """The entry the replacement retires."""

    older: str


def _words(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _changed(notice: str = "") -> dict[str, Any]:
    return {"notice": notice, "undo": None}


@router.post("/memory", summary="Record an entry", status_code=201)
async def add(body: AddBody, memory: MemoryDep) -> JSONResponse:
    """`repository`, `kind`, `statement` and the optional text fields; `Location` reads it back."""
    fields = body.model_dump(exclude_unset=True)
    for name in ("supersedes", "cites"):
        if name in fields:
            fields[name] = _words(fields[name])
    entry = await memory.add(NewMemory.model_validate(fields), by=OWNER)
    location = f"/api/memory/{entry.repository}/{entry.id}"
    return JSONResponse(
        {**_changed(), "id": entry.id}, status_code=201, headers={"Location": location}
    )


@router.get("/memory/{repository}/{name}", summary="One entry")
async def entry(repository: str, name: str, memory: MemoryDep) -> dict[str, Any]:
    """The entry as the Memory page lists it; 404 when no entry has this name."""
    return _record(await memory.get(repository, name))


@router.patch("/memory/{repository}/{name}", summary="Edit an entry; it counts as reviewed")
async def edit(repository: str, name: str, body: EditBody, memory: MemoryDep) -> dict[str, Any]:
    """Any of kind, statement, why, source, guard, scope; `{}` marks it reviewed."""
    await memory.edit(repository, name, MemoryEdit(**body.model_dump(exclude_unset=True)))
    return _changed()


@router.post("/memory/{repository}/{name}/approve", summary="Approve a proposal")
async def approve(repository: str, name: str, memory: MemoryDep) -> dict[str, Any]:
    """Sessions load it from now on."""
    await memory.approve(repository, name)
    return _changed()


@router.post("/memory/{repository}/{name}/dismiss", summary="Dismiss a proposal")
async def dismiss(repository: str, name: str, memory: MemoryDep) -> dict[str, Any]:
    """It moves to history as dismissed."""
    await memory.dismiss(repository, name)
    return _changed()


async def _offer(undo: UndoService, notice: str, *images: EntryImage) -> Changed:
    return await undo.offer(UNDO_KIND, Restore(images=images).model_dump(mode="json"), notice)


@router.post("/memory/{repository}/{name}/merge", summary="Merge an entry into another")
async def merge(
    repository: str, name: str, body: MergeBody, memory: MemoryDep, undo: UndoDep
) -> Changed:
    """`into`: the id of the entry that keeps it."""
    folded, target, images = await memory.merge_with_images(repository, name, body.into)
    return await _offer(undo, f'Merged "{folded.statement}" into "{target.statement}"', *images)


@router.post("/memory/{repository}/{name}/retire", summary="Retire an entry")
async def retire(
    repository: str, name: str, body: RetireBody, memory: MemoryDep, undo: UndoDep
) -> Changed:
    """`reason`: one line saying why it no longer applies."""
    entry, image = await memory.retire_with_image(repository, name, body.reason)
    return await _offer(undo, f'Retired "{entry.statement}"', image)


@router.post("/memory/{repository}/{name}/supersede", summary="Supersede an entry")
async def supersede(
    repository: str, name: str, body: SupersedeBody, memory: MemoryDep, undo: UndoDep
) -> Changed:
    """Retire the older entry while keeping the replacement's existing links."""
    replacement, older, images = await memory.supersede(repository, name, body.older)
    return await _offer(undo, f'"{replacement.statement}" superseded "{older.statement}"', *images)

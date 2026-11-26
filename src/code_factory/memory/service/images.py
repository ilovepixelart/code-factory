"""Writing entries by explicit patch, and putting the before-images back."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from code_factory.memory.models import EntryImage, EntryPatch, EntryRecord
from code_factory.memory.repository import MemoryRepository
from code_factory.memory.tables import MemoryEntryRow
from code_factory.platform.errors import BadRequestError, ConflictError

# The row's columns that are not named as their record field is.
_COLUMNS = {"until": "until_ticket", "date": "written_on"}
_OWN_MOMENTS = {"created_at", "updated_at"}
_PATCHABLE = set(EntryRecord.model_fields) - _OWN_MOMENTS


def record_of(row: MemoryEntryRow) -> EntryRecord:
    """The row's stored values."""
    values = {name: getattr(row, _COLUMNS.get(name, name)) for name in EntryRecord.model_fields}
    return EntryRecord(**values)


def _values(record: EntryRecord) -> dict[str, Any]:
    return {_COLUMNS.get(name, name): value for name, value in record.model_dump().items()}


def _write(row: MemoryEntryRow, record: EntryRecord) -> None:
    for column, value in _values(record).items():
        setattr(row, column, value)


def _unknown(patch: EntryPatch) -> BadRequestError | None:
    for name in patch.fields:
        if name not in _PATCHABLE:
            known = ", ".join(sorted(_PATCHABLE))
            return BadRequestError(f"{patch.id} has no field {name}; its fields are {known}")
    return None


def _changed(
    patch: EntryPatch, before: EntryRecord | None, context: tuple[str, datetime, date]
) -> EntryRecord:
    """The record the patch leaves; `BadRequestError` naming the entry when it is not one."""
    by, now, today = context
    if before is None:
        new = {"date": today, "created_by": by, "created_at": now}
        new["proposed_by"] = by if patch.fields.get("proposed") else ""
    else:
        new = before.model_dump()
    try:
        return EntryRecord.model_validate({**new, **patch.fields, "updated_at": now})
    except ValidationError as error:
        first = error.errors()[0]
        place = ".".join(str(part) for part in first["loc"])
        raise BadRequestError(f"{patch.id}: {place}: {first['msg']}") from error


async def apply_patches(
    entries: MemoryRepository, patches: Sequence[EntryPatch], context: tuple[str, datetime, date]
) -> list[EntryImage]:
    """Write every patch (rows locked in id order); one before-image per patch, in its order."""
    for patch in patches:
        refusal = _unknown(patch)
        if refusal is not None:
            raise refusal
    keys = [(p.repository, p.id) for p in patches]
    if len(set(keys)) != len(keys):
        raise BadRequestError("a patch names an entry twice; merge its fields into one patch")
    by_key = dict(zip(keys, patches, strict=True))
    images: dict[tuple[str, str], EntryImage] = {}
    for key in sorted(keys):
        patch = by_key[key]
        row = await entries.find(patch.repository, patch.id, for_update=True)
        before = record_of(row) if row is not None else None
        after = _changed(patch, before, context)
        if row is None:
            named = {"repository": patch.repository, "name": patch.id}
            await entries.insert({**named, **_values(after)})
        else:
            _write(row, after)
            await entries.flush()
        images[key] = EntryImage(
            repository=patch.repository, id=patch.id, before=before, updated_at=after.updated_at
        )
    return [images[key] for key in keys]


async def restore_images(entries: MemoryRepository, images: Sequence[EntryImage]) -> None:
    """Put each row back as its image holds it, or delete a row the image says was inserted.

    Every row is checked before any is written: one that is gone or moved on since its image
    refuses the whole restore.
    """
    ordered = sorted(images, key=lambda image: (image.repository, image.id))
    rows = []
    for image in ordered:
        row = await entries.find(image.repository, image.id, for_update=True)
        if row is None or row.updated_at != image.updated_at:
            msg = f"{image.id} changed since the change being undone; nothing was put back"
            raise ConflictError(msg)
        rows.append(row)
    for image, row in zip(ordered, rows, strict=True):
        if image.before is None:
            await entries.remove(row)
        else:
            _write(row, image.before)
    await entries.flush()

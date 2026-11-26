"""What sessions spent: tokens and reported cost, read incrementally from their transcripts.

A transcript that grew is read from where it was read to, one that did not is not read at all, and
a read names the sessions it wants, so a board that has seen thousands of sessions pays for the few
the page draws.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from code_factory.platform.db import UnitOfWork
from code_factory.sessions.adapters import (
    TRANSCRIPT_CHUNK_BYTES,
    TRANSCRIPT_LINE_LIMIT_BYTES,
    TranscriptReader,
)
from code_factory.sessions.models import Usage
from code_factory.sessions.repository import ViewRepository
from code_factory.sessions.rules.usage import Totals, summed, transcript_files

KEPT_TRANSCRIPTS = 500


@dataclass(slots=True)
class _Kept:
    """What a transcript held when last read: its size and time, and how much the totals cover."""

    seen: tuple[int, int] | None = None
    offset: int = 0
    totals: Totals = field(default_factory=Totals)
    # Not UTF-8 text: it counts for nothing.
    unreadable: bool = False


def _json(usage: Usage) -> dict[str, object]:
    return {
        "input": usage.input,
        "output": usage.output,
        "cache_read": usage.cache_read,
        "cache_write": usage.cache_write,
        "cost": usage.cost,
        "reported_at": usage.reported_at,
        "cost_incomplete": usage.cost_incomplete,
    }


class UsageReader:
    """Usage of sessions from their transcripts, with a bounded memory of what was read."""

    def __init__(
        self, uow: UnitOfWork, transcripts: TranscriptReader, *, kept: int = KEPT_TRANSCRIPTS
    ) -> None:
        self._uow = uow
        self._transcripts = transcripts
        self._limit = kept
        self._kept: OrderedDict[str, _Kept] = OrderedDict()

    async def usage(self, session_ids: tuple[str, ...] = ()) -> dict[str, dict[str, object]]:
        """The usage of each named known session (every session when none is named)."""
        async with self._uow() as session:
            found = await ViewRepository(session).transcripts(session_ids or None)
        order = list(dict.fromkeys(session_ids)) if session_ids else list(found)
        return {
            session_id: _json(await self._session_usage(found[session_id]))
            for session_id in order
            if session_id in found
        }

    async def _session_usage(self, transcript: str) -> Usage:
        names = (
            await self._transcripts.listdir(
                str(PurePosixPath(transcript).with_suffix("") / "subagents")
            )
            if transcript
            else []
        )
        return summed(
            [await self._file_usage(path) for path in transcript_files(names, transcript)]
        )

    async def _file_usage(self, path: str) -> Usage:
        status = await self._transcripts.stat(path)
        if status is None:
            return Usage()
        kept = self._kept.pop(path, None) or _Kept()
        if kept.seen != status:
            if status[0] < kept.offset:
                kept = _Kept()
            await self._read(path, status[0], kept)
            kept.seen = status
        self._kept[path] = kept
        return Usage() if kept.unreadable else kept.totals.usage()

    async def _read(self, path: str, size: int, kept: _Kept) -> None:
        """Fold the transcript from `kept.offset` on into `kept`, in chunks cut at a line break."""
        while kept.offset < size and not kept.unreadable:
            chunk = await self._transcripts.read_chunk(path, kept.offset, TRANSCRIPT_CHUNK_BYTES)
            if len(chunk) == TRANSCRIPT_CHUNK_BYTES and kept.offset + len(chunk) < size:
                chunk = await self._whole_lines(path, kept.offset, chunk)
            if not chunk:
                break
            try:
                text = chunk.decode("utf-8")
            except UnicodeDecodeError as error:
                # A half-written last character waits for its rest.
                if error.reason != "unexpected end of data":
                    kept.unreadable = True
                    break
                text = chunk[: error.start].decode("utf-8")
            consumed = kept.totals.absorb_text(text)
            if consumed == 0:
                break
            kept.offset += consumed

    async def _whole_lines(self, path: str, offset: int, chunk: bytes) -> bytes:
        """The chunk cut at its last line break; longer when one line fills it, up to a limit."""
        while chunk.rfind(b"\n") < 0:
            if len(chunk) >= TRANSCRIPT_LINE_LIMIT_BYTES:
                return b""
            more = await self._transcripts.read_chunk(
                path, offset + len(chunk), TRANSCRIPT_CHUNK_BYTES
            )
            if not more:
                return chunk
            chunk += more
        return chunk[: chunk.rfind(b"\n") + 1]

    def trim(self) -> None:
        """Forget the least recently read transcripts past the bound."""
        while len(self._kept) > self._limit:
            self._kept.popitem(last=False)

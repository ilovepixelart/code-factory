"""Private QA cases come from real files in board state."""

from pathlib import Path

import pytest

from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.tickets.service import QaHoldouts


async def test_qa_reads_only_the_named_ticket_file_in_board_state(tmp_path: Path) -> None:
    private = tmp_path / "qa-holdouts"
    private.mkdir()
    (private / "CF-12.md").write_text("Try a replay after switching accounts.")
    service = QaHoldouts(tmp_path)

    assert await service.cases("CF-12") == "Try a replay after switching accounts."
    assert await service.cases("CF-13") is None
    with pytest.raises(BadRequestError):
        await service.cases("../CF-12")


async def test_qa_holdouts_never_follow_a_symlink(tmp_path: Path) -> None:
    private = tmp_path / "qa-holdouts"
    private.mkdir()
    outside = tmp_path / "other.md"
    outside.write_text("outside the private cases folder")
    (private / "CF-12.md").symlink_to(outside)

    holdouts = QaHoldouts(tmp_path)
    with pytest.raises(UnavailableError, match="private QA cases"):
        await holdouts.cases("CF-12")


async def test_qa_refuses_directories_and_oversized_case_files(tmp_path: Path) -> None:
    private = tmp_path / "qa-holdouts"
    private.mkdir()
    (private / "CF-12.md").mkdir()
    (private / "CF-13.md").write_bytes(b"x" * 32_769)
    for ticket in ("CF-12", "CF-13"):
        holdouts = QaHoldouts(tmp_path)
        with pytest.raises(UnavailableError, match="private QA cases"):
            await holdouts.cases(ticket)

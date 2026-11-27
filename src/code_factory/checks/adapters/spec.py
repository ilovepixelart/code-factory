"""Atomically publish a spec receipt in the owner-controlled state directory."""

import os
import secrets
from contextlib import suppress
from pathlib import Path

import anyio


def _publish(state: Path, name: str, proof: str) -> None:
    folder = state / "spec-locks"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".{name}.{secrets.token_hex(8)}"
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        with os.fdopen(os.open(temporary, flags, 0o600, dir_fd=fd), "w", encoding="utf-8") as out:
            out.write(proof)
        with suppress(FileExistsError):
            os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        try:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)


async def publish_receipt(state: Path, name: str, proof: str) -> None:
    """Publish the completed receipt without replacing an owner's or another runner's receipt."""
    await anyio.to_thread.run_sync(_publish, state, name, proof)

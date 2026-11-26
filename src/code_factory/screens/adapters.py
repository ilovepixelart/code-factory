"""Taking captures: the tree a branch shows, and Playwright run by Node on board pages."""

import asyncio
import os
from pathlib import Path

import anyio
from pydantic import SecretStr

from code_factory.platform.errors import BadRequestError, UnavailableError
from code_factory.platform.programs import find_program
from code_factory.screens.rules import image_stem

SCRIPT = Path(__file__).with_name("shoot.cjs")
# The web app's packages, in the checkout this module runs from: Playwright lives there.
NODE_MODULES = Path(__file__).resolve().parents[3] / "web" / "node_modules"
PLACES = (Path("/tmp"), Path("/var/tmp"))  # noqa: S108  # folders a run may write
GIT_S = 30.0
CAPTURE_S = 300.0
NOT_INSTALLED = 3


async def tree_of(root: Path, ref: str) -> str:
    """The tree id of `ref` in the repository at `root`."""
    git = await find_program("git", PLACES)
    if git is None:
        msg = "git is not on PATH"
        raise UnavailableError(msg)
    process = await asyncio.create_subprocess_exec(
        str(git), "-C", str(root), "rev-parse", "--verify", "--quiet", f"{ref}^{{tree}}",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    try:
        out, _ = await asyncio.wait_for(process.communicate(), GIT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        msg = f"{ref} names no commit in {root}"
        raise BadRequestError(msg)
    return out.decode().strip()


async def capture(board: str, folder: Path, pages: list[str], session: SecretStr) -> None:
    """Write each page's light and dark image into `folder` as the signed-in owner."""
    node = await find_program("node", PLACES)
    if node is None:
        msg = "the capture tool needs Node: install Node 26 or later"
        raise UnavailableError(msg)
    triples = [
        word for page in pages
        for word in (page.partition("#")[0], image_stem(page), page.partition("#")[2])
    ]  # fmt: skip
    script = await anyio.to_thread.run_sync(SCRIPT.read_bytes)
    env = {
        **os.environ,
        "NODE_PATH": str(NODE_MODULES),
        # The session goes by the environment, which no other account reads, never an argument.
        "CODE_FACTORY_SHOOT_SESSION": session.get_secret_value(),
    }
    process = await asyncio.create_subprocess_exec(
        str(node), "-", board, str(folder), *triples, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )  # fmt: skip
    try:
        _, err = await asyncio.wait_for(process.communicate(script), CAPTURE_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    if process.returncode == NOT_INSTALLED:
        msg = "the capture tool is not installed: run pnpm --dir web install in the checkout"
        raise UnavailableError(msg)
    if process.returncode != 0:
        msg = f"the capture failed: {err.decode(errors='replace').strip()[:500]}"
        raise UnavailableError(msg)

"""Moving commits between a clone and the main repository, and to origin, never by force."""

from pathlib import Path

from code_factory.git.adapters.runner import NETWORK_TIMEOUT_S, GitRunner
from code_factory.git.models import (
    FETCH_CHECKED_OUT,
    FETCH_NOT_A_COMMIT,
    FETCH_NOT_MOVED,
    FetchRefusedError,
)
from code_factory.git.rules.branches import is_commit_id
from code_factory.platform.errors import UnavailableError


async def clone_tip(runner: GitRunner, root: Path, source: str, ref: str) -> str:
    """The commit id `ls-remote` names for exactly `ref` in the clone at `source`."""
    done = await runner.run(root, ["ls-remote", source, ref], timeout_s=NETWORK_TIMEOUT_S)
    for line in done.stdout.splitlines() if done.ok else []:
        commit, _, name = line.partition("\t")
        if name == ref and is_commit_id(commit):
            return commit
    raise FetchRefusedError(FETCH_NOT_A_COMMIT)


async def fetch_into(runner: GitRunner, root: Path, source: str, refspec: str) -> None:
    """Fetch `refspec` from `source` into `root` with git's object checks, writing nothing else."""
    words = [
        "-c", "transfer.fsckObjects=true", "fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
        "--no-recurse-submodules", "--no-auto-gc", source, refspec,
    ]  # fmt: skip
    async with runner.ref_lock(root):
        done = await runner.run(root, words, timeout_s=NETWORK_TIMEOUT_S)
    if done.ok:
        return
    if "refusing to fetch into" in done.stderr:
        raise FetchRefusedError(FETCH_CHECKED_OUT)
    raise FetchRefusedError(FETCH_NOT_MOVED)


async def take_commit(runner: GitRunner, root: Path, source: str, commit: str) -> None:
    """Take `commit` of `source` into `root` without moving a ref: a commit with all its objects."""
    try:
        await fetch_into(runner, root, source, commit)
    except FetchRefusedError:
        raise FetchRefusedError(FETCH_NOT_A_COMMIT) from None
    kind = await runner.ok(root, ["cat-file", "-t", commit])
    whole = await runner.ok(root, ["rev-list", "--quiet", "--objects", commit, "--not", "--all"])
    if kind != "commit" or whole is None:
        raise FetchRefusedError(FETCH_NOT_A_COMMIT)


async def push_commit(runner: GitRunner, root: Path, head: str, branch: str) -> None:
    """`push origin <head>:refs/heads/<branch>`, never forced; the refusal is git's own words."""
    done = await runner.run(
        root,
        ["push", "--quiet", "origin", f"{head}:refs/heads/{branch}"],
        timeout_s=NETWORK_TIMEOUT_S,
    )
    if not done.ok:
        lines = (done.stderr.strip() or done.stdout.strip()).splitlines()
        msg = f"the push of {branch} failed: {lines[-1] if lines else 'git said nothing'}"
        raise UnavailableError(msg)


async def fetch_origin(runner: GitRunner, root: Path) -> None:
    """`fetch -q origin`; the reason is git's first stderr line."""
    done = await runner.run(root, ["fetch", "-q", "origin"], timeout_s=NETWORK_TIMEOUT_S)
    if not done.ok:
        lines = done.stderr.strip().splitlines()
        why = lines[0] if lines else "git said nothing"
        msg = f"cannot fetch origin: {why}. Check `git remote -v`"
        raise UnavailableError(msg)

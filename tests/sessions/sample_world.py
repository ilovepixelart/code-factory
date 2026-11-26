"""The sample of the previous answers built for real: git folders, a spool and transcripts."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sessions_values import golden, sample_files

GIT = shutil.which("git") or "git"


def git(folder: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603  # a fixed program with fixed words
        [
            GIT,
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=folder,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@dataclass(frozen=True, slots=True)
class World:
    """Where the sample's placeholders point."""

    root: Path
    home: Path
    detached: str  # the revision a detached head shows

    def real(self, text: str) -> str:
        """Text with the placeholders replaced by the real folders."""
        return text.replace("{root}", str(self.root)).replace("{home}", str(self.home))

    def placeholders(self, text: str) -> str:
        """Text with the real folders replaced by the placeholders."""
        return text.replace(str(self.root), "{root}").replace(str(self.home), "{home}")


def build_world(base: Path) -> World:
    """`sample` on main, its linked worktree on feat/CF-2, a detached one and a folder inside."""
    root = base / "sample"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("a")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "first")
    (root / "sub").mkdir()
    git(root, "worktree", "add", "-q", "-b", "feat/CF-2", str(base / "sample-wt"))
    git(root, "worktree", "add", "-q", "--detach", str(base / "sample-detached"))
    home = base / "home"
    for name, text in golden("sample.json")["transcripts"].items():
        path = home / "transcripts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return World(root, home, git(base / "sample-detached", "rev-parse", "HEAD"))


def write_sample_spool(spool: Path, world: World) -> None:
    """The sample's spool files, whole lines and a last line still being written."""
    spool.mkdir(parents=True, exist_ok=True)
    for name, data in sample_files().items():
        (spool / name).write_bytes(world.real(data.decode()).encode())

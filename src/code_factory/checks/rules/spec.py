"""Read the commit and file paths of an owner-issued spec receipt."""

import json
import re
from pathlib import PurePosixPath

_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _relative(path: str) -> bool:
    file = PurePosixPath(path)
    return (
        bool(file.parts)
        and not file.is_absolute()
        and file.as_posix() == path
        and ".." not in file.parts
        and "\0" not in path
    )


def receipt_files(text: str) -> tuple[str, list[str]]:
    """The sealed commit and its named paths, or an error for an invalid receipt."""
    data = json.loads(text)
    invalid = "the spec receipt must name a commit and at least one locked file"
    if not isinstance(data, dict):
        raise TypeError(invalid)
    commit, files = data.get("commit"), data.get("files")
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise ValueError(invalid)
    if not isinstance(files, dict) or not files:
        raise ValueError(invalid)
    for path, digest in files.items():
        if not _relative(path) or not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            msg = f"the spec receipt has an invalid file entry for {path!r}"
            raise ValueError(msg)
    return commit, list(files)

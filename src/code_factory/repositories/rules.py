"""Pure rules for the name and root of a tracked repository."""

import posixpath
from pathlib import PurePath

from code_factory.platform.errors import BadRequestError


def name_of(root: PurePath) -> str:
    """The name a repository is addressed by in every URL: its folder name."""
    return root.name


def checked_root(path: PurePath) -> PurePath:
    """The absolute root with trailing separators and dot segments removed.

    Symlinks are not resolved: the caller hands the main checkout it already resolved.
    """
    if not path.is_absolute():
        msg = f"{path} is not an absolute path"
        raise BadRequestError(msg)
    # normpath keeps exactly two leading slashes, which name the same folder as one.
    root = type(path)("/" + posixpath.normpath(path.as_posix()).lstrip("/"))
    if not name_of(root):
        msg = f"{root} has no folder name to track under"
        raise BadRequestError(msg)
    return root

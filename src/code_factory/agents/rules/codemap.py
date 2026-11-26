"""The code map a Spec or Build run is given: the repository's tracked files by folder."""

from collections import defaultdict
from pathlib import PurePosixPath

MAP_LINES = 200
FILES_SHOWN = 12


def code_map(files: list[str], limit: int = MAP_LINES) -> str:
    """The tracked files by folder, each folder with its count and its first files, sorted.

    At most `limit` lines; a map cut short says how many folders it left out. Empty for no files.
    """
    folders: dict[str, list[str]] = defaultdict(list)
    for name in files:
        path = PurePosixPath(name)
        folders[str(path.parent)].append(path.name)
    if not folders:
        return ""
    lines = ["Code map (tracked files by folder; read a file before relying on it):"]
    ordered = sorted(folders)
    for at, folder in enumerate(ordered):
        if len(lines) >= limit:
            lines.append(f"... {len(ordered) - at} more folders")
            break
        names = sorted(folders[folder])
        shown = ", ".join(names[:FILES_SHOWN])
        more = f", +{len(names) - FILES_SHOWN} more" if len(names) > FILES_SHOWN else ""
        where = "." if folder == "." else f"{folder}/"
        lines.append(f"- {where} ({len(names)}): {shown}{more}")
    return "\n".join(lines)

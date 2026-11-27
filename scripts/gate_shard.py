"""Print the test files of one shard of a test folder, for CI jobs that run a suite in parts.

A file belongs to shard `crc32(path) % n + 1`: stable across runs and machines, needing no record
of past timings, and close to even for a folder of many files.
"""

import argparse
import re
import sys
import zlib
from pathlib import Path

SHARD = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


def shard_of(path: str, count: int) -> int:
    """The 1-based shard of `count` that the test file `path` belongs to."""
    return zlib.crc32(path.encode()) % count + 1


def main() -> int:
    """Print one test file per line, sorted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("shard", help="INDEX/COUNT, such as 1/2")
    args = parser.parse_args()
    found = SHARD.fullmatch(args.shard)
    if found is None or int(found[1]) > int(found[2]):
        parser.error(f"the shard is INDEX/COUNT with 1 <= INDEX <= COUNT, not {args.shard!r}")
    index, count = int(found[1]), int(found[2])
    files = sorted(str(p) for p in args.folder.rglob("test_*.py"))
    sys.stdout.writelines(f"{path}\n" for path in files if shard_of(path, count) == index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

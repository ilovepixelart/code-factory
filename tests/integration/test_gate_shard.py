import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gate_shard.py"


def shard(folder: Path, spec: str, hash_seed: str = "0") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # the checked-in shard helper on a fixture folder
        [sys.executable, str(SCRIPT), str(folder), spec],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
    )


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    for name in (
        "a/test_one.py",
        "a/test_two.py",
        "b/test_three.py",
        "test_four.py",
        "c/helper.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")
    return tmp_path


@pytest.mark.parametrize("count", [1, 2, 3])
def test_every_test_file_is_in_exactly_one_shard(folder: Path, count: int) -> None:
    shards = [shard(folder, f"{i}/{count}").stdout.splitlines() for i in range(1, count + 1)]

    listed = [path for files in shards for path in files]
    expected = {str(p) for p in folder.rglob("test_*.py")}
    assert sorted(listed) == sorted(expected)
    assert len(listed) == len(set(listed)) == 4


def test_two_processes_split_a_folder_the_same_way_whatever_their_hash_seed(folder: Path) -> None:
    """Each CI job is its own process: a split by Python's salted hash() would differ."""
    first, second = shard(folder, "1/2", hash_seed="1"), shard(folder, "1/2", hash_seed="2")

    assert first.stdout.splitlines() == second.stdout.splitlines()


@pytest.mark.parametrize("spec", ["0/2", "3/2", "1", "a/b", "1/0"])
def test_a_shard_outside_its_count_is_refused(folder: Path, spec: str) -> None:
    result = shard(folder, spec)

    assert result.returncode == 2
    assert "the shard is INDEX/COUNT" in result.stderr


@pytest.mark.parametrize("count", [2, 3])
def test_the_shards_of_a_large_folder_are_close_to_even(tmp_path: Path, count: int) -> None:
    for number in range(40):
        (tmp_path / f"m{number % 7}").mkdir(exist_ok=True)
        (tmp_path / f"m{number % 7}" / f"test_case_{number}.py").write_text("")

    sizes = [len(shard(tmp_path, f"{i}/{count}").stdout.splitlines()) for i in range(1, count + 1)]

    assert sum(sizes) == 40
    assert min(sizes) > 0
    assert max(sizes) <= 0.7 * 40

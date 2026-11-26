"""Tracking a repository from the browser: `POST /api/repositories`."""

from pathlib import Path

import httpx

from git_support import commit, git


def _repository(root: Path) -> Path:
    root.mkdir(parents=True)
    git(root, "init", "-q")
    return root


async def test_a_git_repository_is_tracked_and_listed(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    root = _repository(tmp_path / "shop")

    answer = await client.post("/api/repositories", json={"path": root.as_posix()})

    assert (answer.status_code, answer.json(), answer.headers["location"]) == (
        201,
        {"name": "shop", "path": root.resolve().as_posix()},
        "/api/repositories",
    )
    assert "shop" in (await client.get("/api/repositories")).json()


async def test_a_worktree_tracks_its_main_checkout(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    root = _repository(tmp_path / "shop")
    commit(root, "Start")
    worktree = tmp_path / "elsewhere"
    git(root, "worktree", "add", "-q", worktree.as_posix())

    answer = await client.post("/api/repositories", json={"path": worktree.as_posix()})

    assert answer.json() == {"name": "shop", "path": root.resolve().as_posix()}


async def test_a_missing_folder_is_refused_with_a_sentence(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    missing = tmp_path / "nowhere"

    answer = await client.post("/api/repositories", json={"path": missing.as_posix()})

    assert (answer.status_code, answer.json()["detail"]) == (
        400,
        f"{missing.as_posix()} does not exist: give the folder of a git repository",
    )


async def test_a_file_is_refused_as_not_a_folder(client: httpx.AsyncClient, tmp_path: Path) -> None:
    file = tmp_path / "notes.txt"
    file.write_text("x")

    answer = await client.post("/api/repositories", json={"path": file.as_posix()})

    assert (answer.status_code, answer.json()["detail"]) == (
        400,
        f"{file.as_posix()} is not a folder: give the folder of a git repository",
    )


async def test_a_folder_outside_git_is_refused(client: httpx.AsyncClient, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    answer = await client.post("/api/repositories", json={"path": plain.as_posix()})

    assert (answer.status_code, answer.json()["detail"]) == (
        400,
        (
            f"{plain.as_posix()} is not a git repository: run git init there, "
            "or give the repository's folder"
        ),
    )


async def test_a_relative_path_is_refused(client: httpx.AsyncClient) -> None:
    answer = await client.post("/api/repositories", json={"path": "shop"})

    assert (answer.status_code, answer.json()["detail"]) == (400, "shop is not an absolute path")


async def test_an_unknown_field_is_refused(client: httpx.AsyncClient, tmp_path: Path) -> None:
    root = _repository(tmp_path / "shop")

    answer = await client.post("/api/repositories", json={"path": root.as_posix(), "name": "x"})

    assert answer.status_code == 400
    assert "shop" not in (await client.get("/api/repositories")).json()

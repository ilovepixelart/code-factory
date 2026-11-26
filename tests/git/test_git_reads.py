"""Facts, changes, merges, merge checks and tree names against real git."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from code_factory.git.models import GitFacts
from code_factory.git.service import GitService, reads
from git_support import commit, git, write


async def test_facts_run_exactly_five_git_calls_whatever_the_branch_count(
    service: GitService, root: Path
) -> None:
    for n in range(6):
        git(root, "branch", f"b{n}")
    before = service._runner.calls  # counts the processes, not a private result
    facts = await service.facts("sample")
    assert service._runner.calls - before == 5
    assert {"main", "b0", "b5"} <= facts.local
    assert facts.known


async def test_two_concurrent_callers_share_one_read_and_invalidate_reads_again(
    service: GitService,
) -> None:
    import asyncio  # noqa: PLC0415

    before = service._runner.calls
    await asyncio.gather(service.facts("sample"), service.facts("sample"))
    assert service._runner.calls - before == 5
    service.invalidate("sample")
    await service.facts("sample")
    assert service._runner.calls - before == 10


async def test_a_file_named_like_the_default_branch_does_not_make_facts_unknown(
    service: GitService, root: Path
) -> None:
    write(root, "main", "a file called main\n")
    assert (await service.facts("sample")).known


async def test_a_merged_pull_request_is_merged_and_a_branch_ahead_is_not(
    service: GitService, root: Path
) -> None:
    git(root, "checkout", "-q", "-b", "feat/x")
    commit(root, "Two", **{"two.txt": "2\n"})
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge pull request #1 from owner/feat/x", "feat/x")
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-q", "-b", "feat/y")
    commit(root, "Three", **{"three.txt": "3\n"})
    git(root, "checkout", "-q", "main")
    facts = await service.facts("sample")
    from code_factory.git.rules.facts import is_merged  # noqa: PLC0415

    assert is_merged("CF-1", "feat/x", facts)
    assert not is_merged("CF-2", "feat/y", facts)
    state = await service.branch_state("sample", "feat/y")
    assert (state.ahead, state.merged, state.pushed) == (1, False, False)


async def test_changes_show_the_branch_diff_and_none_for_a_missing_branch(
    service: GitService, root: Path
) -> None:
    git(root, "checkout", "-q", "-b", "feat/c")
    commit(root, "Edit", **{"readme.md": "hello\nworld\n", "new.txt": "n\n"})
    git(root, "checkout", "-q", "main")
    view = await service.changes("sample", "feat/c")
    assert [(f.path, [(x.kind, x.number, x.text) for x in f.lines]) for f in view.files] == [
        ("new.txt", [("added", 1, "n")]),
        ("readme.md", [("kept", 1, "hello"), ("added", 2, "world")]),
    ]
    assert (view.cut, view.limit, view.branch, view.default_branch) == (
        False,
        400,
        "feat/c",
        "main",
    )
    assert (await service.changes("sample", "nope")).files == []
    assert (await service.changes("sample", "")).files == []


def _forge_parent(graph: Path, commit_id: str, new_parent_id: str) -> None:
    """Rewrite one commit's first parent in a commit-graph file (CDAT chunk, git's format docs)."""
    data = bytearray(graph.read_bytes())
    chunks = data[6]
    table = {
        bytes(data[8 + 12 * i : 12 + 12 * i]): int.from_bytes(
            data[12 + 12 * i : 20 + 12 * i], "big"
        )
        for i in range(chunks)
    }
    oids = table[b"OIDL"]
    count = int.from_bytes(data[table[b"OIDF"] + 255 * 4 : table[b"OIDF"] + 256 * 4], "big")
    ids = [data[oids + 20 * i : oids + 20 * i + 20].hex() for i in range(count)]
    entry = table[b"CDAT"] + 36 * ids.index(commit_id)
    data[entry + 20 : entry + 24] = ids.index(new_parent_id).to_bytes(4, "big")
    graph.write_bytes(bytes(data))


async def test_a_forged_commit_graph_does_not_move_the_fork_point(
    service: GitService, root: Path
) -> None:
    base = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "-b", "feat/g")
    tip = commit(root, "One", **{"one.txt": "1\n"})
    git(root, "checkout", "-q", "main")
    main = commit(root, "Main moves", **{"m.txt": "m\n"})
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "-c", "core.commitGraph=true", "commit-graph", "write", "--reachable")
    graph = root / ".git/objects/info/commit-graph"
    graph.chmod(0o644)
    _forge_parent(graph, tip, main)
    assert git(root, "merge-base", main, tip) == main  # the forged graph does fool plain git
    assert await service.fork_point("sample", tip) == base


async def test_a_binary_file_has_no_lines_in_changes(service: GitService, root: Path) -> None:
    git(root, "checkout", "-q", "-b", "feat/b")
    (root / "img.bin").write_bytes(b"\x00\x01\x02")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "bin")
    git(root, "checkout", "-q", "main")
    view = await service.changes("sample", "feat/b")
    assert [(f.path, f.lines) for f in view.files] == []


async def test_merges_list_a_real_merged_pull_request(service: GitService, root: Path) -> None:
    git(root, "checkout", "-q", "-b", "ticket/cf-7")
    commit(root, "Work", **{"w.txt": "w\n"})
    git(root, "checkout", "-q", "main")
    git(
        root,
        "merge",
        "-q",
        "--no-ff",
        "-m",
        "Merge pull request #7 from owner/ticket/cf-7",
        "ticket/cf-7",
    )
    found = await service.merges("sample", 0)
    assert [(m.pull, m.branch, m.ticket) for m in found] == [(7, "ticket/cf-7", "CF-7")]
    assert await service.merges("sample", 10**12) == []


async def test_tree_name_changes_with_an_untracked_file_and_not_with_an_ignored_one(
    service: GitService, root: Path
) -> None:
    commit(root, "Ignore", **{".gitignore": "*.log\n"})
    first = await service.tree_name(root)
    write(root, "debug.log", "x")
    assert await service.tree_name(root) == first
    write(root, "new.txt", "x")
    assert await service.tree_name(root) != first


async def test_merge_conflicts_name_files_store_the_pair_and_a_failure_stores_nothing(
    service: GitService, root: Path
) -> None:
    git(root, "checkout", "-q", "-b", "a")
    tip_a = commit(root, "A", **{"readme.md": "a\n"})
    git(root, "checkout", "-q", "main")
    git(root, "checkout", "-q", "-b", "b")
    tip_b = commit(root, "B", **{"readme.md": "b\n"})
    git(root, "checkout", "-q", "main")
    check = await service.merge_conflicts("sample", tip_b, tip_a)
    assert check is not None
    assert (check.clean, check.files) == (False, ["readme.md"])
    calls = service._runner.calls
    again = await service.merge_conflicts("sample", tip_a, tip_b)
    assert again == check
    assert service._runner.calls == calls  # the pair came from its row
    assert await service.merge_conflicts("sample", "0" * 40, tip_a) is None
    assert await service.merge_conflicts("sample", "0" * 40, tip_a) is None
    git(root, "checkout", "-q", "-b", "c")
    tip_c = commit(root, "C", **{"other.txt": "c\n"})
    clean = await service.merge_conflicts("sample", tip_c, tip_a)
    assert clean is not None
    assert clean.clean
    cutoff = datetime.now(UTC) + timedelta(days=1)
    assert await service.forget_merge_checks(cutoff) == 2


async def test_plain_reads(service: GitService, root: Path) -> None:
    head = git(root, "rev-parse", "HEAD")
    assert await service.has_commit("sample", head)
    assert not await service.has_commit("sample", "0" * 40)
    assert await service.is_ancestor("sample", head, head)
    assert await service.head_commit("sample") == head
    assert await service.tracked_files("sample") == ["readme.md"]
    assert await service.read_file_at("sample", head, "readme.md") == "hello\n"
    assert await service.subject("sample", head) == "Start"
    assert await service.origin_main_tip("sample") == head
    assert await service.remote_tip("sample", "main") == head
    assert (await service.remote_url("sample") or "").endswith("sample-origin.git")
    assert await service.main_checkout(root) == root


async def test_a_timed_out_read_makes_facts_unknown_instead_of_raising(
    service: GitService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reads, "LOG_TIMEOUT_S", 1e-6)
    assert not (await service.facts("sample")).known


async def test_an_old_read_finishing_does_not_end_the_share_of_a_newer_one(
    service: GitService, monkeypatch: pytest.MonkeyPatch
) -> None:
    gates = [asyncio.Event(), asyncio.Event()]
    started: list[int] = []
    facts = await service.facts("sample")

    async def slow(repository: str) -> GitFacts:  # noqa: ARG001
        number = len(started)
        started.append(number)
        await gates[number].wait()
        return facts

    monkeypatch.setattr(service, "_read_facts", slow)
    first = asyncio.create_task(service.facts("sample"))
    await asyncio.sleep(0.05)
    service.invalidate("sample")
    second = asyncio.create_task(service.facts("sample"))
    await asyncio.sleep(0.05)
    gates[0].set()
    await first
    third = asyncio.create_task(service.facts("sample"))
    await asyncio.sleep(0.05)
    assert started == [0, 1]  # the third caller shares the second read
    gates[1].set()
    await asyncio.gather(second, third)

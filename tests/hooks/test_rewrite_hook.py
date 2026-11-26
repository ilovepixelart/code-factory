"""The rewrite hook as a runtime starts it (`python -I -S`), against real git and a real origin."""

import json
import time
from pathlib import Path

import pytest

import code_factory.hooks.adapters.hook as hook_module
from code_factory.hooks.rules import rewrite_guard
from git_support import commit, git
from hooks_support import BRANCH, GOLDEN, bash, run_hook, ticket_tree


def denied(out: str) -> str:
    said = json.loads(out)["hookSpecificOutput"]
    assert said["hookEventName"] == "PreToolUse"
    assert said["permissionDecision"] == "deny"
    return str(said["permissionDecisionReason"])


def test_an_amend_of_a_pushed_commit_is_denied_with_the_golden_answer(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree

    ran = run_hook("rewrite", bash("git commit --amend", tree), cwd=tree)

    assert (ran.code, ran.err) == (0, "")
    assert ran.out == (GOLDEN / "rewrite_denied.json").read_text(encoding="utf-8")


def test_an_amend_of_a_commit_origin_does_not_have_prints_nothing(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree
    commit(tree, "local only", **{"b.txt": "b\n"})

    ran = run_hook("rewrite", bash("git commit --amend --no-edit", tree), cwd=tree)

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_a_rebase_past_a_pushed_commit_is_denied_and_one_of_unpushed_commits_is_allowed(
    tmp_path: Path,
) -> None:
    tree = ticket_tree(tmp_path).tree
    commit(tree, "local only", **{"b.txt": "b\n"})

    past = run_hook("rewrite", bash("git rebase main", tree), cwd=tree)
    onto_the_pushed = run_hook("rewrite", bash(f"git rebase origin/{BRANCH}", tree), cwd=tree)
    reset_keeping = run_hook("rewrite", bash("git reset --hard HEAD~0", tree), cwd=tree)

    assert denied(past.out).endswith(
        "pushed this commit to origin/ticket/cf-1. Add a new commit instead of rewriting it."
    )
    assert onto_the_pushed.out == ""
    assert reset_keeping.out == ""


def test_a_reset_below_the_pushed_commit_is_denied(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree

    ran = run_hook("rewrite", bash("git reset --hard HEAD~1", tree), cwd=tree)

    assert "the board has pushed this commit" in denied(ran.out)


def test_a_forced_push_is_denied_even_when_the_tree_has_no_origin(tmp_path: Path) -> None:
    tree = tmp_path / "x" / ".code-factory" / "worktrees" / "CF-9"
    tree.mkdir(parents=True)
    git(tree, "init", "-q")

    ran = run_hook("rewrite", bash("git push --force origin HEAD", tree), cwd=tree)

    assert denied(ran.out) == (
        "code-factory: refused `git push --force origin HEAD`: the board pushes this branch and "
        "a forced push can replace a commit it has pushed. Add a new commit instead."
    )


def test_a_branch_origin_does_not_have_may_be_rewritten(tmp_path: Path) -> None:
    root = ticket_tree(tmp_path).root
    tree = root / ".code-factory" / "worktrees" / "CF-2"
    git(root, "worktree", "add", "-q", "-b", "ticket/cf-2", str(tree))
    commit(tree, "mine", **{"m.txt": "m\n"})

    ran = run_hook("rewrite", bash("git commit --amend --no-edit", tree), cwd=tree)

    assert ran.out == ""


def test_the_main_checkout_is_not_a_ticket_tree(tmp_path: Path) -> None:
    made = ticket_tree(tmp_path)
    git(made.root, "checkout", "-q", "-b", "other")
    commit(made.root, "pushed", **{"o.txt": "o\n"})
    git(made.root, "push", "-q", "origin", "other")

    ran = run_hook("rewrite", bash("git commit --amend --no-edit", made.root), cwd=made.root)

    assert ran.out == ""


def test_dash_c_from_elsewhere_into_a_ticket_tree_is_judged_there(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    direct = run_hook("rewrite", bash(f"git -C {tree} commit --amend", elsewhere), cwd=elsewhere)
    nested = run_hook(
        "rewrite", bash(f"sh -c 'cd {tree} && git commit --amend'", elsewhere), cwd=elsewhere
    )

    assert "pushed this commit" in denied(direct.out)
    assert "pushed this commit" in denied(nested.out)


def test_a_pull_that_rebases_and_the_deletion_of_the_branch_are_denied(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree

    pull = run_hook("rewrite", bash("git pull --rebase", tree), cwd=tree)
    delete = run_hook("rewrite", bash(f"git push origin --delete {BRANCH}", tree), cwd=tree)
    other = run_hook("rewrite", bash("git push origin --delete other", tree), cwd=tree)

    assert "origin/ticket/cf-1" in denied(pull.out)
    assert "deletes or moves it" in denied(delete.out)
    assert other.out == ""


def test_the_guard_runs_nothing_the_repository_configures(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree
    marker = tmp_path / "ran"
    git(tree, "remote", "set-url", "origin", "ssh://example.invalid/origin.git")
    git(tree, "config", "core.sshCommand", f"touch {marker}; false")
    git(tree, "config", "core.fsmonitor", f"touch {marker}; true")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "reference-transaction").write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    (hooks / "reference-transaction").chmod(0o755)
    git(tree, "config", "core.hooksPath", str(hooks))
    git(tree, "config", "alias.rev-parse", f"!touch {marker}")

    ran = run_hook("rewrite", bash("git commit --amend --no-edit", tree), cwd=tree)

    assert "the board has pushed this commit" in denied(ran.out)
    assert not marker.exists()


def test_environment_variables_that_point_git_elsewhere_are_not_followed(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")

    ran = run_hook(
        "rewrite",
        bash("git commit --amend --no-edit", tree),
        cwd=tree,
        env={"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)},
    )

    assert "the board has pushed this commit" in denied(ran.out)


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        "not json {git",
        "[1, 2]",
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": {"command": 5}}',
        '{"tool_name": "Read", "tool_input": {"command": "git commit --amend"}, "cwd": "/"}',
        '{"tool_name": "Bash", "tool_input": {"command": "git commit --amend"}, "cwd": "/gone"}',
    ],
)
def test_a_payload_the_hook_cannot_use_prints_nothing_and_exits_zero(
    tmp_path: Path, stdin: str
) -> None:
    ran = run_hook("rewrite", stdin, cwd=tmp_path)

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_a_payload_without_cwd_is_judged_from_the_process_folder(tmp_path: Path) -> None:
    tree = ticket_tree(tmp_path).tree
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit --amend"}})

    ran = run_hook("rewrite", payload, cwd=tree)

    assert "pushed this commit" in denied(ran.out)


def test_a_payload_with_no_git_bytes_exits_before_importing_json(tmp_path: Path) -> None:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/"})

    ran = run_hook("rewrite", payload, cwd=tmp_path, flags=("-X", "importtime"))
    with_git = run_hook(
        "rewrite", bash("git status", tmp_path), cwd=tmp_path, flags=("-X", "importtime")
    )

    assert (ran.code, ran.out) == (0, "")
    assert "| json" not in ran.err
    assert "| json" in with_git.err


def test_an_unknown_hook_name_does_nothing(tmp_path: Path) -> None:
    ran = run_hook("nonsense", "{}", cwd=tmp_path)

    assert (ran.code, ran.out, ran.err) == (0, "", "")


def test_many_allowed_rewrites_before_a_refused_one_do_not_exhaust_the_judging(
    tmp_path: Path,
) -> None:
    tree = ticket_tree(tmp_path).tree
    allowed = [f"git rebase origin/{BRANCH}"] * 3 + [
        "git rebase --onto origin/main origin/main"
    ] * 3
    command = " ; ".join([*allowed, "git commit --amend --no-edit"])

    ran = run_hook("rewrite", bash(command, tree), cwd=tree)

    assert "pushed this commit" in denied(ran.out)


def test_a_git_that_stalls_reads_as_no_state_within_its_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "git").write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    (fake / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:/usr/bin:/bin")
    monkeypatch.setattr(hook_module, "GIT_CALL_S", 0.3)
    started = time.monotonic()

    state = hook_module.BranchReader(rewrite_guard).state(str(tmp_path), None)

    assert state is None
    assert time.monotonic() - started < 3

"""Which shell commands rewrite a commit origin already has, and what a branch state makes of them.

The command tables and the sentences are written by hand from the guard's specification.
"""

import pytest

from code_factory.git.rules.folders import board_tree_of
from code_factory.hooks.rules.rewrite_guard import (
    AMEND,
    FORCE,
    PULL_REBASE,
    BranchState,
    Rewrite,
    delete,
    in_ticket_tree,
    move,
    rebase,
    refusal,
    reset,
    rewrites,
)

TREE = "/r/.code-factory/worktrees/CF-1"
BRANCH = "ticket/cf-1"


def pushed() -> BranchState:
    return BranchState(BRANCH, head_pushed=True, keeps_pushed=False)


def found(command: str) -> list[Rewrite]:
    return rewrites(command, TREE)


def refused(command: str) -> str | None:
    """The refusal of the only rewrite `command` holds, when the board has pushed everything."""
    seen = found(command)
    assert len(seen) <= 1, f"{command}: {seen}"
    return refusal(seen[0], pushed()) if seen else None


def judged(command: str, state: BranchState | None) -> list[str | None]:
    return [refusal(rewrite, state) for rewrite in found(command)]


REFUSED_FORMS = [
    "git commit --amend",
    "git commit --amend --no-edit",
    "git commit -a --amend -m x",
    "git commit --am",
    "git commit -m x --amend",
    "git -C /r/.code-factory/worktrees/CF-1 commit --amend",
    "git -c user.name=x commit --amend",
    "sh -c 'git commit --amend --no-edit'",
    'bash -lc "cd /tmp && git commit --amend"',
    "git add -A && git commit --amend",
    "git add -A;git commit --amend",
    "true || git commit --amend",
    "(git commit --amend)",
    "FOO=1 git commit --amend",
    "env GIT_EDITOR=true git commit --amend",
    "git push --force",
    "git push --force-with-lease origin HEAD",
    "git push --force-with-lease=ticket/cf-1 origin HEAD",
    "git push -f",
    "git push -uf origin HEAD",
    "git push origin +HEAD:ticket/cf-1",
    "git push origin +ticket/cf-1",
    "git rebase main",
    "git rebase -i main",
    "git rebase --onto main HEAD~2",
    "git rebase --onto=main HEAD~2",
    "git rebase --root",
    "git reset --hard HEAD~1",
    "git reset --soft HEAD^",
    "git reset HEAD~3",
]

ALLOWED_FORMS = [
    "git commit -m 'fix --amend'",
    'git commit -m "git commit --amend"',
    "git commit -m --amend",
    "git commit -am 'say --amend'",
    "git commit -mfoo",
    "git commit --message=--amend",
    "git commit -- --amend",
    "git add -- --amend",
    "git commit -m x",
    "git commit -a --allow-empty -m x",
    "git commit --all",
    "git commit --a",
    "git commit --author=x -m y",
    "git push",
    "git push -u origin ticket/cf-1",
    "git push origin HEAD:ticket/cf-1",
    "git status",
    "git",
    "git --version",
    "git -C",
    "git -C /tmp",
    "git log --oneline",
    "echo git commit --amend",
    "echo 'git push --force'",
    "cat -- --force",
    "git rebase --abort",
    "git rebase --continue",
    "git reset",
    "git reset --hard",
    "git reset -- src/lib.rs",
    "git reset HEAD~1 -- src/lib.rs",
    "git reset -p",
    "git fetch --force",
    "sh -c 'git status'",
    "ls",
    "",
]


@pytest.mark.parametrize("command", REFUSED_FORMS)
def test_every_rewriting_form_is_found_and_refused_on_a_pushed_branch(command: str) -> None:
    assert refused(command) is not None


@pytest.mark.parametrize("command", ALLOWED_FORMS)
def test_every_other_form_holds_no_rewrite(command: str) -> None:
    assert found(command) == []


def test_the_refusal_names_the_command_and_says_to_add_a_commit() -> None:
    assert refused("git commit --amend --no-edit") == (
        "code-factory: refused `git commit --amend --no-edit`: the board has pushed this commit "
        "to origin/ticket/cf-1. Add a new commit instead of rewriting it."
    )


def test_a_forced_push_is_refused_even_when_origin_has_no_such_branch() -> None:
    said = refusal(found("git push --force")[0], None)

    assert said == (
        "code-factory: refused `git push --force`: the board pushes this branch and a forced "
        "push can replace a commit it has pushed. Add a new commit instead."
    )


def test_an_amend_of_a_commit_origin_does_not_have_is_allowed() -> None:
    amend = found("git commit --amend")[0]
    unpushed = BranchState(BRANCH, head_pushed=False, keeps_pushed=False)

    assert refusal(amend, unpushed) is None
    assert refusal(amend, None) is None
    assert refusal(amend, pushed()) is not None


@pytest.mark.parametrize("command", ["git rebase origin/ticket/cf-1", "git reset --hard HEAD~1"])
def test_a_rebase_or_reset_that_keeps_the_pushed_commits_is_allowed(command: str) -> None:
    rewrite = found(command)[0]

    assert refusal(rewrite, BranchState(BRANCH, head_pushed=True, keeps_pushed=True)) is None
    assert refusal(rewrite, BranchState(BRANCH, head_pushed=True, keeps_pushed=None)) is None
    assert refusal(rewrite, None) is None
    assert refusal(rewrite, pushed()) is not None


def test_a_rebase_with_no_base_replays_onto_the_upstream_and_is_allowed() -> None:
    rewrite = found("git rebase")[0]

    assert rewrite.action == rebase(None)
    assert refusal(rewrite, pushed()) is None


def test_a_root_rebase_is_refused_whatever_the_revision_check_says() -> None:
    keeps = BranchState(BRANCH, head_pushed=False, keeps_pushed=True)

    assert refusal(found("git rebase --root")[0], keeps) is not None


def test_the_revision_a_command_moves_to_is_named() -> None:
    commands = [
        "git rebase main",
        "git rebase --onto abc123 main",
        "git reset --hard origin/main",
        "git rebase --root",
        "git commit --amend",
    ]

    assert [found(c)[0].revision() for c in commands] == [
        "main",
        "abc123",
        "origin/main",
        None,
        None,
    ]


def test_the_directory_follows_dash_c_and_cd() -> None:
    commands = [
        "git commit --amend",
        "git -C ../CF-2 commit --amend",
        "git -C /elsewhere commit --amend",
        "cd /elsewhere && git commit --amend",
        "cd .. && cd CF-3 && git commit --amend",
        "sh -c 'cd sub && git commit --amend'",
    ]

    assert [found(c)[0].dir for c in commands] == [
        "/r/.code-factory/worktrees/CF-1",
        "/r/.code-factory/worktrees/CF-2",
        "/elsewhere",
        "/elsewhere",
        "/r/.code-factory/worktrees/CF-3",
        "/r/.code-factory/worktrees/CF-1/sub",
    ]


def test_a_parent_step_above_the_root_stays_at_the_root() -> None:
    assert rewrites("cd ../../.. && git commit --amend", "/a")[0].dir == "/"


def test_a_chain_reports_each_rewrite_in_order() -> None:
    chain = "git commit --amend && git push --force; git reset HEAD~1"

    assert [r.action for r in found(chain)] == [AMEND, FORCE, reset("HEAD~1")]


def test_a_shell_inside_a_shell_is_followed_four_levels_and_no_deeper() -> None:
    def nested(levels: int) -> str:
        command = "git commit --amend"
        for _ in range(levels):
            command = "sh -c '" + command.replace("'", "'\\''") + "'"
        return command

    assert len(found(nested(4))) == 1
    assert found(nested(5)) == []


PULL_REBASES = [
    "git pull --rebase",
    "git pull --reb",
    "git pull -r",
    "git pull -xr",
    "git pull --rebase origin main",
    "git pull origin main --rebase",
    "git pull --rebase=true",
    "git pull --rebase=merges",
    "git pull --rebase=interactive",
    "git pull -rv",
    "git pull -s ours --rebase",
    "git -C /r/.code-factory/worktrees/CF-1 pull --rebase",
    "sh -c 'git pull --rebase'",
]

PULL_MERGES = [
    "git pull",
    "git pull --ff-only",
    "git pull origin main",
    "git pull --no-rebase",
    "git pull --rebase=false",
    "git pull --re",
    "git pull -v",
    "git pull -s ours",
    "git pull -sr",
    "git pull -Xrenormalize",
    "git pull -srecursive",
    "git pull -- --rebase",
]


@pytest.mark.parametrize("command", PULL_REBASES)
def test_a_pull_that_rebases_is_refused(command: str) -> None:
    assert "origin/ticket/cf-1" in (refused(command) or "")


@pytest.mark.parametrize("command", PULL_MERGES)
def test_a_pull_that_does_not_rebase_is_allowed(command: str) -> None:
    assert judged(command, pushed()) == [None] * len(found(command))


@pytest.mark.parametrize(
    "command",
    [
        "git -c pull.rebase=true pull",
        "git -c pull.rebase=merges pull",
        "git -c pull.rebase=interactive pull origin main",
        "git -c Pull.Rebase=TRUE pull",
        "git -c pull.rebase pull",
        "git -c branch.ticket/cf-1.rebase=true pull",
        "git -c user.name=x -c pull.rebase=true pull",
        "git --config-env=pull.rebase=REBASE pull",
        "git --config-env pull.rebase=REBASE pull",
        "git --config-env=branch.x.rebase=REBASE pull",
    ],
)
def test_a_pull_made_rebasing_by_a_command_line_setting_is_refused(command: str) -> None:
    assert refused(command) is not None


@pytest.mark.parametrize(
    "command",
    [
        "git -c pull.rebase=false pull",
        "git -c pull.rebase=no pull",
        "git -c pull.rebase= pull",
        "git -c pull.ff=only pull",
        "git -c rebase.autosquash=true pull",
        "git -c branch.x.merge=true pull",
        "git -c pull.rebase=true pull --no-rebase",
        "git -c pull.rebase=true pull --rebase=false",
        "git --config-env=pull.ff=FF pull",
        "git -c pull.rebase=true fetch",
        "git -c pull.rebase=true status",
    ],
)
def test_a_pull_not_made_rebasing_by_a_setting_is_allowed(command: str) -> None:
    assert judged(command, pushed()) == [None] * len(found(command))


def _says_delete_or_move(command: str) -> str:
    return (
        f"code-factory: refused `{command}`: the board has pushed this branch to "
        f"origin/ticket/cf-1 and this command deletes or moves it. Add a new commit instead."
    )


@pytest.mark.parametrize(
    "command",
    [
        "git push --delete origin ticket/cf-1",
        "git push origin --delete ticket/cf-1",
        "git push -d origin ticket/cf-1",
        "git push origin --delete refs/heads/ticket/cf-1",
        "git push origin --delete other ticket/cf-1",
        "git push origin :ticket/cf-1",
        "git push origin :refs/heads/ticket/cf-1",
        "git push origin :other :ticket/cf-1",
        "git branch -D ticket/cf-1",
        "git branch -D other ticket/cf-1",
        "git branch -d -f ticket/cf-1",
        "git branch -d -f other ticket/cf-1",
        "git branch --delete --force ticket/cf-1",
        "git branch -f ticket/cf-1 main",
        "git branch --force ticket/cf-1 abc123",
        "git branch -f ticket/cf-1",
        "git update-ref refs/heads/ticket/cf-1 abc123",
        "git update-ref -m why refs/heads/ticket/cf-1 abc123",
        "git update-ref --no-deref refs/heads/ticket/cf-1 abc123",
        "git update-ref -d refs/heads/ticket/cf-1",
        "git update-ref HEAD abc123",
        "git push origin :heads/ticket/cf-1",
        "git push --delete origin heads/ticket/cf-1",
        "git branch -D heads/ticket/cf-1",
        "git branch -f refs/heads/ticket/cf-1 main",
    ],
)
def test_deleting_or_moving_the_tickets_own_branch_is_refused(command: str) -> None:
    assert refused(command) == _says_delete_or_move(command)


@pytest.mark.parametrize(
    "command",
    [
        "git push --delete origin other",
        "git push origin --delete other",
        "git push origin :other",
        "git push origin :refs/heads/other",
        "git push origin --delete ticket/cf-10",
        "git push origin :ticket/cf-1/sub",
        "git branch -D other",
        "git branch -f other",
        "git branch -f other main",
        "git branch -d -f other",
        "git update-ref refs/heads/other abc123",
        "git update-ref -d refs/heads/other",
        "git update-ref -m ticket/cf-1 refs/heads/other abc123",
        "git update-ref refs/remotes/origin/ticket/cf-1 abc123",
        "git update-ref refs/tags/ticket/cf-1 abc123",
        "git push origin :heads/other/cf-1",
        "git push origin :refs/heads/other/cf-1",
        "git push --delete origin other/cf-1",
        "git push --delete origin refs/heads/cf-1",
        "git branch -D heads/other",
        "git update-ref refs/heads/other/cf-1 abc123",
        "git update-ref refs/heads/cf-1 abc123",
        "git push origin :refs/tags/ticket/cf-1",
    ],
)
def test_deleting_or_moving_another_branch_is_allowed(command: str) -> None:
    assert judged(command, pushed()) == [None] * len(found(command))


@pytest.mark.parametrize(
    "command",
    [
        "git push origin ticket/cf-1",
        "git push origin HEAD:ticket/cf-1",
        "git push origin :",
        "git push origin",
        "git push",
        "git branch",
        "git branch --list",
        "git branch -d",
        "git branch -d ticket/cf-1",
        "git branch new main",
        "git branch -m ticket/cf-1 renamed",
        "git branch -m -f ticket/cf-1 renamed",
        "git branch --move --force ticket/cf-1 renamed",
        "git branch -C -f ticket/cf-1 copy",
        "git branch -u origin/ticket/cf-1",
        "git branch --show-current",
        "git update-ref",
    ],
)
def test_branch_and_push_commands_that_delete_nothing_are_allowed(command: str) -> None:
    assert judged(command, pushed()) == [None] * len(found(command))


@pytest.mark.parametrize(
    "command",
    [
        "git pull --rebase",
        "git push origin --delete ticket/cf-1",
        "git branch -D ticket/cf-1",
        "git branch -f ticket/cf-1 main",
        "git update-ref refs/heads/ticket/cf-1 abc123",
        "git update-ref --stdin",
    ],
)
def test_the_branch_rules_judge_only_a_branch_origin_has(command: str) -> None:
    local_only = BranchState(BRANCH, head_pushed=False, keeps_pushed=None)

    assert judged(command, local_only)[0] is not None
    assert judged(command, None) == [None]


def test_a_deletion_or_move_names_the_branches_it_touches() -> None:
    commands = (
        "git push origin --delete a refs/heads/b; git push origin :c; git branch -D d e; "
        "git branch -f f x; git update-ref refs/heads/g y; git update-ref HEAD z; git pull -r"
    )

    assert [r.action for r in found(commands)] == [
        delete(("a", "b")),
        delete(("c",)),
        delete(("d", "e")),
        move("f"),
        move("g"),
        move("HEAD"),
        PULL_REBASE,
    ]


@pytest.mark.parametrize(
    "command", ["git update-ref --stdin", "git update-ref -z --stdin", "git update-ref --stdin -z"]
)
def test_an_update_ref_batch_is_taken_to_move_the_checked_out_branch(command: str) -> None:
    assert found(command)[0].action == move("HEAD")
    assert refused(command) is not None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git commit -m x -- --amend", 0),
        ("git commit --message --amend", 0),
        ("git commit -F --amend", 0),
        ("git commit -am --amend", 0),
        ("git commit -m x --amend", 1),
        ("git commit --a", 0),
        ("git commit --amen", 1),
        ("git commit --amend=x", 0),
    ],
)
def test_a_commit_amends_only_on_an_unambiguous_prefix_outside_a_valued_option(
    command: str, expected: int
) -> None:
    assert len(found(command)) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git -c a=b -C /x commit --amend", "/x"),
        ("git --git-dir /x/.git commit --amend", TREE),
        ("git --work-tree /w --namespace n commit --amend", TREE),
    ],
)
def test_git_options_that_take_a_value_do_not_hide_the_command(command: str, expected: str) -> None:
    assert found(command)[0].dir == expected


@pytest.mark.parametrize(
    "command",
    [
        "sudo git commit --amend",
        "nohup git commit --amend",
        "time git commit --amend",
        "exec git commit --amend",
        "command git commit --amend",
        "if git commit --amend; then true; fi",
        "echo hi\ngit commit --amend",
        "echo x | git commit --amend",
        "echo x `git commit --amend`",
        "X=1 Y=2 /usr/bin/git commit --amend",
    ],
)
def test_wrappers_and_separators_do_not_hide_a_rewrite(command: str) -> None:
    assert len(found(command)) == 1


@pytest.mark.parametrize(
    "command",
    [
        "git commit --amend",
        "git\tcommit  --amend",
        "git commit --'amend'",
        'git commit --"amend"',
        "git comm\\it --amend",
    ],
)
def test_quoting_is_read_as_a_shell_reads_it(command: str) -> None:
    assert len(found(command)) == 1


def test_a_backslash_in_double_quotes_escapes_only_a_quote_or_a_backslash() -> None:
    assert found('git commit -m "a\\nb" --amend')[0].command == "git commit -m a\\nb --amend"
    assert found('git commit -m "a\\"b" --amend')[0].command == 'git commit -m a"b --amend'


# Known gaps of a guard that reads words, not a shell: today's answers, pinned so a hardening
# shows as a diff here.
@pytest.mark.parametrize(
    "command",
    [
        "git$IFS commit --amend",
        "eval 'git commit --amend'",
        "$(echo git) commit --amend",
        "xargs git commit --amend",
        "g=git; $g commit --amend",
        "alias ga='git commit --amend'; ga",
        "sh script.sh",
    ],
)
def test_forms_the_guard_does_not_detect_today(command: str) -> None:
    assert found(command) == []


@pytest.mark.parametrize(
    ("path", "inside"),
    [
        ("/r/.code-factory/worktrees/CF-1", True),
        ("/r/.code-factory/worktrees/CF-1/src/deep", True),
        ("/r/.code-factory/worktrees-x/CF-1", False),
        ("/r/.code-factory/worktrees", False),
        ("/r/.code-factory", False),
        ("/r/src", False),
        ("/r", False),
        ("/", False),
        ("/x/.code-factory/worktrees/CF-1/.code-factory/worktrees/CF-2", True),
    ],
)
def test_a_tree_is_found_by_path_components_not_substrings(path: str, inside: bool) -> None:
    assert in_ticket_tree(path) is inside
    assert (board_tree_of(path) is not None) is inside  # the git module's rule agrees

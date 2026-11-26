"""srt's settings for each kind of work the board contains. The worktree setup's JSON is the
previous implementation's recorded one, with this module's secret list; each other kind differs
by the single thing its docstring names."""

import json
from collections.abc import Sequence
from typing import Any

import pytest

from code_factory.agents.models.constants import SECRET_FILES, SECRET_VARIABLES
from code_factory.agents.rules.places import SANDBOX_DOMAINS
from code_factory.agents.rules.settings import BOARD_VARIABLES, RUNTIME_VARIABLES
from code_factory.agents.rules.srt import (
    git_settings,
    preview_settings,
    process_settings,
    tree_settings,
)

STATE = ["/h/state"]
KEYS = ["ANTHROPIC_WORK_API_KEY"]


def tree(
    path: str = "/r/.worktrees/CF-1", hosts: Sequence[str] = SANDBOX_DOMAINS
) -> dict[str, Any]:
    return json.loads(
        tree_settings(
            state=STATE,
            home="/h/state",
            tree=path,
            log="/r/.worktrees/CF-1.setup.log",
            scratch="/scratch/x-1",
            keys=KEYS,
            hosts=hosts,
            denied=["/r/.worktrees/CF-1/.git"],
        )
    )


def deny(name: str) -> dict[str, str]:
    return {"name": name, "mode": "deny"}


def test_the_worktree_setups_settings_are_the_recorded_ones() -> None:
    assert tree() == {
        "network": {
            "allowedDomains": [
                "pypi.org:443",
                "files.pythonhosted.org:443",
                "registry.npmjs.org:443",
            ],
            "deniedDomains": [],
            "allowLocalBinding": False,
        },
        "filesystem": {
            "denyRead": ["/h/state", *SECRET_FILES],
            "allowRead": ["/r/.worktrees/CF-1.setup.log"],
            "allowWrite": ["/r/.worktrees/CF-1", "/scratch/x-1"],
            "denyWrite": ["/r/.worktrees/CF-1/.git"],
        },
        "credentials": {
            "envVars": [
                *(deny(name) for name in SECRET_VARIABLES),
                *(deny(name) for name in RUNTIME_VARIABLES),
                *(deny(name) for name in BOARD_VARIABLES),
                deny("ANTHROPIC_WORK_API_KEY"),
            ]
        },
    }


def test_a_tree_inside_the_state_folder_may_also_be_read() -> None:
    inside = tree(path="/h/state/checks/t1")
    assert inside["filesystem"]["allowRead"] == [
        "/r/.worktrees/CF-1.setup.log",
        "/h/state/checks/t1",
    ]
    beside = tree(path="/h/state-other/t1")
    assert beside["filesystem"]["allowRead"] == ["/r/.worktrees/CF-1.setup.log"]


def test_checks_reach_no_host_and_the_setup_reaches_the_ones_named() -> None:
    assert tree(hosts=[])["network"]["allowedDomains"] == []
    assert tree(hosts=["a.example.com:443"])["network"]["allowedDomains"] == ["a.example.com:443"]


def test_only_the_previews_settings_allow_listening_on_this_machine() -> None:
    common: dict[str, Any] = {
        "state": STATE,
        "home": "/h/state",
        "tree": "/r/t",
        "log": "/l",
        "scratch": "/m",
        "keys": [],
        "denied": ["/r/t/.git"],
    }
    preview = json.loads(preview_settings(**common))
    checks = json.loads(tree_settings(**common, hosts=[]))
    git = json.loads(git_settings(**common))
    assert preview["network"]["allowLocalBinding"] is True
    assert checks["network"]["allowLocalBinding"] is False
    assert git["network"]["allowLocalBinding"] is False
    assert preview["network"]["allowedDomains"] == []
    assert git["network"]["allowedDomains"] == []


def test_a_gits_settings_deny_what_the_boards_git_reads_outside_the_sandbox() -> None:
    common: dict[str, Any] = {
        "state": STATE,
        "home": "/h/state",
        "tree": "/r/t",
        "log": "/l",
        "scratch": "/m",
        "keys": [],
    }
    clone = json.loads(git_settings(**common, denied=["/r/.git", "/r/t/.git/config"]))
    assert clone["filesystem"]["denyWrite"] == ["/r/.git", "/r/t/.git/config"]
    assert clone["filesystem"]["allowWrite"] == ["/r/t", "/m"]


KINDS = {
    "tree": lambda **c: tree_settings(**c, hosts=[]),
    "preview": preview_settings,
    "git": git_settings,
}


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_kind_of_work_denies_every_secret_file_the_state_folder_and_every_key(
    kind: str,
) -> None:
    settings = json.loads(
        KINDS[kind](
            state=["/h/state", "/p/h/state"],
            home="/h/state",
            tree="/r/t",
            log="/l",
            scratch="/m",
            keys=["OPENROUTER_API_KEY"],
            denied=[],
        )
    )
    reads = settings["filesystem"]["denyRead"]
    assert reads == ["/h/state", "/p/h/state", *SECRET_FILES]
    names = [item["name"] for item in settings["credentials"]["envVars"]]
    assert names == [
        *SECRET_VARIABLES,
        *RUNTIME_VARIABLES,
        *BOARD_VARIABLES,
        "OPENROUTER_API_KEY",
    ]


def test_a_contained_codex_process_reaches_its_one_host_and_writes_its_branch_and_the_locks() -> (
    None
):
    settings = json.loads(
        process_settings(
            state=STATE,
            hosts=["127.0.0.1:1234"],
            writes=["/r/t", "/r/.git/worktrees/t", "/r/.git/objects", "/h/state-locks"],
            denied=["/r/t/.git"],
            reads=["/h/state/runs/r1.log"],
            keys=KEYS,
        )
    )
    assert settings["network"] == {
        "allowedDomains": ["127.0.0.1:1234"],
        "deniedDomains": [],
        "allowLocalBinding": False,
    }
    assert settings["filesystem"] == {
        "denyRead": ["/h/state", *SECRET_FILES],
        "allowRead": ["/h/state/runs/r1.log"],
        "allowWrite": ["/r/t", "/r/.git/worktrees/t", "/r/.git/objects", "/h/state-locks"],
        "denyWrite": ["/r/t/.git"],
    }
    assert deny("ANTHROPIC_WORK_API_KEY") in settings["credentials"]["envVars"]

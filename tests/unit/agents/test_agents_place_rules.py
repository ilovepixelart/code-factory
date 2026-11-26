"""Where a run may write and reach: the state folder in each of its forms, the lock folder, what
the board reads outside the sandbox, the hosts a worktree setup may reach, the identity of a run's
commits and the one folder a codex program opens. Expectations come from the previous
implementation's tests (`codex_program.rs`, `runs.rs`) or are worked by hand."""

import pytest

from code_factory.agents.models.connections import ConnectionDefinition
from code_factory.agents.models.places import GitPlaces
from code_factory.agents.rules.places import (
    AGENT_EMAIL,
    AGENT_NAME,
    SANDBOX_DOMAINS,
    agent_identity,
    allowed_domains,
    checkout_denials,
    codex_program_folder,
    contained,
    contained_line,
    host_port,
    kept_writes,
    lock_folder,
    lock_folders,
    model_host,
    run_writes,
    state_forms,
)
from code_factory.platform.errors import BadRequestError


def test_the_state_folder_is_given_in_its_own_form_and_its_resolved_one_once_each() -> None:
    assert state_forms("/h/state", "/private/h/state") == ["/h/state", "/private/h/state"]
    assert state_forms("/h/state", "/h/state") == ["/h/state"]
    assert state_forms("state", "/h/state") == ["/h/state"]
    assert state_forms("rel", "rel") == []


def test_the_lock_folder_sits_beside_the_state_folder_under_its_name_with_locks() -> None:
    assert lock_folder("/h/state") == "/h/state-locks"
    assert lock_folder("/h/state/") == "/h/state-locks"
    assert lock_folder("/") is None
    assert lock_folder("") is None


def test_the_lock_folders_are_the_given_one_and_the_one_whose_parent_resolves_elsewhere() -> None:
    assert lock_folders("/h/state", "/h") == ["/h/state-locks"]
    assert lock_folders("/h/state", "/private/h") == ["/h/state-locks", "/private/h/state-locks"]
    assert lock_folders("state", "/h") == []


def test_a_clone_may_not_write_the_main_repositorys_git_folder_a_worktree_only_the_kept_ones() -> (
    None
):
    assert kept_writes(["/r/.git/config"], main=None) == ["/r/.git/config"]
    assert kept_writes(["/t/.git/config"], main="/r/.git") == ["/r/.git", "/t/.git/config"]


def test_a_checkout_denies_the_boards_files_and_a_ticket_tree_none() -> None:
    names = ["config.toml", ".worktrees"]
    assert checkout_denials("/r", names, is_checkout=True, clones="/r/.git/clones") == [
        "/r/config.toml",
        "/r/.worktrees",
        "/r/.git/clones",
    ]
    assert checkout_denials("/r", names, is_checkout=True, clones=None) == [
        "/r/config.toml",
        "/r/.worktrees",
    ]
    assert checkout_denials("/r/.worktrees/CF-1", names, is_checkout=False, clones="/x") == []


def test_without_domains_named_the_package_registries_on_the_https_port_are_reached() -> None:
    registries = ["pypi.org:443", "files.pythonhosted.org:443", "registry.npmjs.org:443"]
    assert list(SANDBOX_DOMAINS) == registries
    assert allowed_domains(None) == registries
    assert allowed_domains("pypi.org") == registries
    assert allowed_domains(["a.example.com", 3]) == registries


def test_only_host_names_ending_in_letters_are_allowed_domains() -> None:
    named = [
        "pypi.org",
        "*.example.com",
        "a.b.example.co:8443",
        "localhost",
        "a.localhost",
        "10.0.0.1",
        "intranet",
        "x.y.LOCALHOST:80",
        "bad host.org",
    ]
    assert allowed_domains(named) == ["pypi.org", "*.example.com", "a.b.example.co:8443"]
    assert allowed_domains([]) == []


@pytest.mark.parametrize("entry", ["a.example.com:443", "127.0.0.1:1234", "h:1", "h:65535"])
def test_an_entry_with_a_host_and_a_port_is_taken(entry: str) -> None:
    assert host_port(entry)


@pytest.mark.parametrize(
    "entry",
    ["a.example.com", "*:443", ":443", "h:0", "h:65536", "h:x", "h:", "a b:1", "a/b:1", "h:-1"],
)
def test_an_entry_without_a_valid_port_or_with_a_wildcard_host_is_refused(entry: str) -> None:
    assert not host_port(entry)


def test_a_commit_carries_the_agent_identity_unless_a_well_formed_author_is_named() -> None:
    default = {
        "GIT_AUTHOR_NAME": AGENT_NAME,
        "GIT_AUTHOR_EMAIL": AGENT_EMAIL,
        "GIT_COMMITTER_NAME": AGENT_NAME,
        "GIT_COMMITTER_EMAIL": AGENT_EMAIL,
    }
    assert agent_identity(None) == default
    assert agent_identity("Bot <bot@example.com>") == {
        "GIT_AUTHOR_NAME": "Bot",
        "GIT_AUTHOR_EMAIL": "bot@example.com",
        "GIT_COMMITTER_NAME": "Bot",
        "GIT_COMMITTER_EMAIL": "bot@example.com",
    }
    assert agent_identity("  Bot  < bot@example.com > ")["GIT_AUTHOR_NAME"] == "Bot"
    for malformed in (
        "Bot",
        " <bot@example.com>",
        "Bot <bot>",
        "Bot <a<b@example.com>",
        "",
        "Bot <x@y",
    ):
        assert agent_identity(malformed) == default, malformed
    assert list(default) == [
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    ]


def test_a_contained_line_hands_srt_one_shell_line_and_its_settings_file() -> None:
    assert contained_line("/bin/srt", "/s/x.json", "echo hi") == [
        "/bin/srt",
        "--settings",
        "/s/x.json",
        "-c",
        "echo hi",
    ]


def test_a_contained_command_quotes_each_word_and_unsets_the_no_proxy_variables() -> None:
    line = contained(
        "/bin/srt", "/s/x.json", ["codex", "app-server", "a b", "it's", "", "x_1.2/y"]
    )[4]
    assert line == "env -u NO_PROXY -u no_proxy codex app-server 'a b' 'it'\"'\"'s' '' x_1.2/y"


HOME, STATE = "/owner", "/owner/.local/state/factory"
BIN = "/owner/.codex/packages/standalone/releases/1/bin"


def program(path: str, resolved: str | None = None) -> str | None:
    return codex_program_folder(
        HOME,
        STATE,
        path,
        lambda found: resolved if resolved is not None and found == path else found,
    )


def test_a_program_under_the_codex_folder_opens_only_its_own_folder() -> None:
    assert program(f"{BIN}/codex") == BIN


def test_a_program_outside_every_denied_folder_opens_nothing() -> None:
    assert program("/opt/homebrew/bin/codex") is None
    assert program("/owner/.codexish/bin/codex") is None


def test_a_program_directly_in_the_codex_folder_is_refused_with_where_it_is() -> None:
    with pytest.raises(BadRequestError) as caught:
        program("/owner/.codex/codex")
    assert str(caught.value) == (
        "codex is installed at /owner/.codex/codex, in /owner/.codex, which a board run is "
        "denied; a board run needs codex installed outside /owner/.codex"
    )


@pytest.mark.parametrize("path", ["/owner/.ssh/bin/codex", f"{STATE}/bin/codex"])
def test_a_program_in_another_denied_folder_is_refused(path: str) -> None:
    with pytest.raises(BadRequestError):
        program(path)


def test_the_folder_is_the_one_the_resolved_program_is_in() -> None:
    assert program("/owner/.local/bin/codex", f"{BIN}/codex") == BIN


def test_a_connections_host_and_port_are_the_one_host_a_contained_run_reaches() -> None:
    def on(kind: str, base: str) -> str:
        return model_host(ConnectionDefinition(name="c", kind=kind, base_url=base))

    assert on("ollama", "http://127.0.0.1:11434") == "127.0.0.1:11434"
    assert on("custom", "http://localhost") == "localhost:80"
    assert on("lm-studio", "http://localhost:1234") == "localhost:1234"
    assert on("openrouter", "https://openrouter.ai/api") == "openrouter.ai:443"
    assert on("custom", "http://127.0.0.1:9000/v1") == "127.0.0.1:9000"
    with pytest.raises(BadRequestError):
        on("ollama", "http://10.0.0.5:11434")


def test_a_run_writes_its_trees_the_objects_and_its_branchs_ref_lock_and_log() -> None:
    places = GitPlaces(
        worktree="/r/t", admin="/r/.git/worktrees/t", common="/r/.git", branch="feat/CF-1"
    )
    assert run_writes(places) == [
        "/r/t",
        "/r/.git/worktrees/t",
        "/r/.git/objects",
        "/r/.git/refs/heads/feat/CF-1",
        "/r/.git/refs/heads/feat/CF-1.lock",
        "/r/.git/logs/refs/heads/feat/CF-1",
    ]


def test_a_run_with_no_branch_writes_no_ref() -> None:
    places = GitPlaces(worktree="/r/t", admin="/r/.git/worktrees/t", common="/r/.git", branch="")
    assert run_writes(places) == ["/r/t", "/r/.git/worktrees/t", "/r/.git/objects"]

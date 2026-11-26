"""A checks container mount may not reach a folder a run is denied. The secret list is the previous
implementation's, written out here so a dropped or added entry fails a named test."""

from pathlib import PurePosixPath

import pytest

from code_factory.settings.rules.secrets import (
    SECRET_FILES,
    VALIDATION_HOME,
    container_mount_problem,
)

EXPECTED_SECRETS = [
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gh",
    "~/.docker/config.json",
    "~/.netrc",
    "~/.npmrc",
    "~/.pypirc",
    "~/.git-credentials",
    "~/.omp",
    "~/.local/share/opencode/auth.json",
    "~/.kube",
    "~/.azure",
    "~/.pi/agent",
    "~/.codex",
    "~/.claude",
    "~/.claude.json",
]
REACHES = "the host folder is, holds or is in the home folder or a secret folder"


def test_the_secret_list_is_the_previous_one() -> None:
    assert list(SECRET_FILES) == EXPECTED_SECRETS


@pytest.mark.parametrize("secret", EXPECTED_SECRETS)
def test_a_mount_of_a_secret_inside_it_or_holding_it_is_refused(secret: str) -> None:
    folder = secret.removeprefix("~/")
    parent = folder.rpartition("/")[0]
    assert container_mount_problem(f"{secret}:/x") == f"{secret}:/x: {REACHES}"
    assert container_mount_problem(f"{secret}/sub:/x") == f"{secret}/sub:/x: {REACHES}"
    assert container_mount_problem(f"/home/{folder}:/x") == f"/home/{folder}:/x: {REACHES}"
    if parent:
        assert container_mount_problem(f"~/{parent}:/x") == f"~/{parent}:/x: {REACHES}"


@pytest.mark.parametrize("entry", ["~/:/x", "/home:/x", "/:/x"])
def test_the_home_folder_is_never_mounted_whole(entry: str) -> None:
    problem = container_mount_problem(entry)
    assert problem is not None
    assert problem.startswith(f"{entry}: ")


@pytest.mark.parametrize(
    "entry",
    [
        "~/.cargo/registry:/usr/local/cargo/registry",
        "~/.claude-notes:/x",
        "/srv/cache:/cache",
        "~/.sshd:/x",
    ],
)
def test_a_mount_that_touches_no_secret_is_accepted(entry: str) -> None:
    assert container_mount_problem(entry) is None


def test_a_mount_spelled_in_another_case_reaches_the_same_folder_on_a_case_insensitive_disk() -> (
    None
):
    homes = (VALIDATION_HOME, PurePosixPath("/Users/alex"))
    for entry in ("~/.SSH:/x", "/Users/alex/.Ssh:/x", "/users/alex:/x", "/USERS/ALEX/.aws/x:/x"):
        assert container_mount_problem(entry, homes) is not None, entry
    for entry in ("/Users/alex/.Cargo/registry:/x", "/Users/Other:/x", "~/Work/.cache:/x"):
        assert container_mount_problem(entry, homes) is None, entry


def test_a_doubled_leading_slash_reaches_the_same_folder() -> None:
    homes = (VALIDATION_HOME, PurePosixPath("/Users/alex"))
    for entry in ("//Users/alex/.ssh:/x", "//Users/alex:/x", "//home/.aws:/x"):
        assert container_mount_problem(entry, homes) is not None, entry
    assert container_mount_problem("//srv/cache:/x", homes) is None


HOMES = (VALIDATION_HOME, PurePosixPath("/home/alex"))
ELSEWHERE = "the host folder is in /home but not in the home folder"


@pytest.mark.parametrize("host", ["/home/bob/x", "/HOME/bob", "//home/bob/x"])
def test_an_explicit_host_in_another_folder_of_home_is_refused(host: str) -> None:
    assert container_mount_problem(f"{host}:/x", HOMES) == f"{host}:/x: {ELSEWHERE}"


@pytest.mark.parametrize("entry", ["/home/alex/work:/x", "~/work:/x", "/homes/bob:/x", "/srv:/x"])
def test_a_host_in_the_home_folder_or_outside_home_is_not_refused_as_elsewhere(entry: str) -> None:
    assert container_mount_problem(entry, HOMES) is None


def test_a_home_that_is_unknown_exempts_nothing_in_home() -> None:
    homes = (VALIDATION_HOME, VALIDATION_HOME)
    assert container_mount_problem("/home/bob/x:/x", homes) == f"/home/bob/x:/x: {ELSEWHERE}"

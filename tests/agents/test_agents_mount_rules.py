"""The checks container's command line and its mounts, each expectation taken from the previous
implementation's tests (`agent_rules.rs`) or worked by hand."""

import hashlib

import pytest

from code_factory.agents.models.constants import SECRET_FILES
from code_factory.agents.rules.mounts import (
    checks_image_tag,
    container_mount,
    in_container,
    mount_reaches_secrets,
    secret_paths,
)
from code_factory.platform.errors import BadRequestError

HOME = "/Users/o"
EXPECTED = (
    "expected <host folder>:<folder inside>, the host one absolute or under ~/, "
    "the inside one absolute"
)
REACHES = "the host folder is, holds or is in the home folder or a secret folder"


def refusal(entry: str) -> str:
    with pytest.raises(BadRequestError) as caught:
        container_mount(entry, HOME)
    return str(caught.value)


def test_a_plain_run_mounts_the_tree_writable_and_the_readonly_folders_read_only() -> None:
    words = in_container(
        "/usr/bin/docker",
        "img",
        "/w/t",
        readonly=["/r/.git"],
        mounts=[],
        variables=["HOME=/h", "PATH=/bin"],
        command="true",
    )
    assert " ".join(words) == (
        "/usr/bin/docker run --rm --network none --init --volume /w/t:/w/t:rw --volume "
        "/r/.git:/r/.git:ro --workdir /w/t --env HOME=/h img /bin/sh -c true"
    )


def test_the_container_keeps_its_own_path_and_temporary_folder_and_mounts_read_only() -> None:
    words = in_container(
        "/usr/bin/docker",
        "img",
        "/w/t",
        readonly=[],
        mounts=[("/h/.cargo/registry", "/usr/local/cargo/registry")],
        variables=["TMPDIR=/var/folders/x/T/", "LANG=C", "PATH=/x"],
        command="true",
    )
    assert " ".join(words) == (
        "/usr/bin/docker run --rm --network none --init --volume /w/t:/w/t:rw --volume "
        "/h/.cargo/registry:/usr/local/cargo/registry:ro --workdir /w/t --env LANG=C img "
        "/bin/sh -c true"
    )


@pytest.mark.parametrize(
    ("tree", "readonly", "mounts", "named"),
    [
        ("/w/a:b", [], [], "/w/a:b"),
        ("/w/t", ["/r/x:y"], [], "/r/x:y"),
        ("/w/t", [], [("/h/a:b", "/in")], "/h/a:b"),
        ("/w/t", [], [("/h/a", "/in:side")], "/in:side"),
    ],
)
def test_a_path_holding_a_colon_is_refused_wherever_it_is(
    tree: str, readonly: list[str], mounts: list[tuple[str, str]], named: str
) -> None:
    with pytest.raises(BadRequestError) as caught:
        in_container(
            "/usr/bin/docker",
            "img",
            tree,
            readonly=readonly,
            mounts=mounts,
            variables=[],
            command="true",
        )
    assert str(caught.value) == f"the checks container cannot mount {named}, which holds ':'"


def test_a_mount_is_a_host_folder_and_an_absolute_place_inside() -> None:
    assert container_mount("~/.cargo/registry:/usr/local/cargo/registry", HOME) == (
        "/Users/o/.cargo/registry",
        "/usr/local/cargo/registry",
    )
    assert container_mount("/opt/cache:/cache", HOME) == ("/opt/cache", "/cache")


@pytest.mark.parametrize(
    "entry", ["cache:/cache", "/cache:cache", "/cache", "/a:/b:/c", "/a/../b:/c", "/:/c", "/a:/"]
)
def test_any_other_shape_is_refused_naming_what_is_expected(entry: str) -> None:
    assert refusal(entry) == f"{entry}: {EXPECTED}"


@pytest.mark.parametrize(
    "entry", ["~/:/c", "/Users:/c", "~/.ssh:/c", "~/.ssh/keys:/c", "~/.config:/c", "~/.claude:/c"]
)
def test_a_mount_never_reaches_the_home_folder_or_a_secret(entry: str) -> None:
    assert refusal(entry) == f"{entry}: {REACHES}"


def test_a_cache_beside_the_secrets_is_taken() -> None:
    assert container_mount("~/.cargo/registry:/r", HOME)[0] == "/Users/o/.cargo/registry"
    assert container_mount("~/.config/pnpm:/r", HOME)[0] == "/Users/o/.config/pnpm"
    assert mount_reaches_secrets("/Users/o/.aws", HOME, [])
    assert not mount_reaches_secrets("/Users/o/.cache", HOME, [])


def test_a_resolved_secret_folder_is_reached_from_either_side() -> None:
    resolved = ["/vault/keys"]
    assert mount_reaches_secrets("/vault/keys/a", HOME, resolved)
    assert mount_reaches_secrets("/vault", HOME, resolved)
    assert not mount_reaches_secrets("/vault2", HOME, resolved)
    assert mount_reaches_secrets("/Users/o//.aws/", HOME, [])


def test_every_secret_file_is_a_path_under_the_home_folder() -> None:
    paths = secret_paths(HOME)
    assert len(paths) == len(SECRET_FILES)
    assert "/Users/o/.ssh" in paths
    assert "/Users/o/.claude.json" in paths
    assert all(path.startswith("/Users/o/") for path in paths)
    assert secret_paths("/Users/o/")[0] == "/Users/o/.ssh"


def test_the_image_tag_is_the_first_16_hex_of_the_sha256_of_the_container_file() -> None:
    assert checks_image_tag(b"abc") == "code-factory-checks:ba7816bf8f01cfea"
    text = b"FROM x\nRUN y\n"
    assert checks_image_tag(text) == f"code-factory-checks:{hashlib.sha256(text).hexdigest()[:16]}"
    assert checks_image_tag(b"a") != checks_image_tag(b"b")

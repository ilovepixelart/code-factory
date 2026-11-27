"""The contained runner: a command on code a run wrote, in srt or as it is."""

import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from code_factory.platform.contained import ContainedRunner, Work
from code_factory.platform.errors import UnavailableError

FAKE_SRT = """#!/bin/sh
# what srt is given: --settings FILE -c COMMAND; shows the file and its text, then runs the command
echo "$2"
/bin/cat "$2"
exec /bin/sh -c "$4"
"""
SETTINGS = '{"filesystem": "rules"}\n'


@dataclass
class Policy:
    sandbox: bool = True
    nvmrc_text: str | None = None
    folders: list[Path] = field(default_factory=list)

    async def sandboxed(self, repository: str) -> bool:  # noqa: ARG002
        return self.sandbox

    async def nvmrc(self, repository: str) -> str | None:  # noqa: ARG002
        return self.nvmrc_text

    def places(self) -> list[Path]:
        return self.folders


@dataclass
class Rules:
    """The sandbox settings port: records which settings were asked for."""

    asked: list[tuple[str, str, bool | None]] = field(default_factory=list)
    refusal: str | None = None
    seen_temporary: list[Path] = field(default_factory=list)

    def _answer(self, kind: str, temporary: Path, hosts: bool | None = None) -> str:
        self.asked.append((kind, "repo", hosts))
        self.seen_temporary.append(temporary)
        if self.refusal is not None:
            raise UnavailableError(self.refusal)
        return SETTINGS

    async def tree_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path, *, reaches_hosts: bool
    ) -> str:
        del repository, tree, log
        return self._answer("tree", temporary, reaches_hosts)

    async def git_settings(self, repository: str, tree: Path, log: Path, temporary: Path) -> str:
        del repository, tree, log
        return self._answer("git", temporary)

    async def preview_settings(
        self, repository: str, tree: Path, log: Path, temporary: Path
    ) -> str:
        del repository, tree, log
        return self._answer("preview", temporary)


@pytest.fixture
def bin_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "bin"
    folder.mkdir()
    folder.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:relative")  # a relative entry is never kept
    return folder


def install_srt(folder: Path) -> None:
    srt = folder / "srt"
    srt.write_text(FAKE_SRT)
    srt.chmod(0o755)


def exists(path: Path) -> bool:
    return path.exists()


def read(path: Path) -> str:
    return path.read_text()


def entries(path: Path) -> list[str]:
    return sorted(entry.name for entry in path.iterdir()) if path.exists() else []


def runner(tmp_path: Path, policy: Policy, rules: Rules) -> ContainedRunner:
    return ContainedRunner(policy=policy, sandbox=rules, state_dir=tmp_path / "state")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    folder = tmp_path / "tree"
    folder.mkdir()
    return folder


async def test_without_the_sandbox_the_command_runs_as_it_is_in_the_tree(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    log = tmp_path / "logs" / "run.log"
    contained = runner(tmp_path, Policy(sandbox=False), Rules())
    code = await contained.run(Work.CHECKS, "repo", 'echo "$PATH"; pwd -P; exit 4', tree, log, 30)
    assert code == 4
    assert read(log).splitlines() == [str(bin_folder), str(tree)]


async def test_a_check_that_requires_the_sandbox_cannot_fall_back_to_plain_execution(
    tmp_path: Path,
    tree: Path,
) -> None:
    log = tmp_path / "run.log"
    contained = runner(tmp_path, Policy(sandbox=False), Rules())

    with pytest.raises(UnavailableError, match="spec checks require the agent sandbox"):
        await contained.run(Work.CHECKS, "repo", "echo ran", tree, log, 30, require_sandbox=True)

    assert not log.exists()


async def test_a_child_never_inherits_the_variables_that_name_a_repository(
    tmp_path: Path, tree: Path, bin_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del bin_folder
    monkeypatch.setenv("GIT_DIR", "/elsewhere")
    log = tmp_path / "run.log"
    await runner(tmp_path, Policy(sandbox=False), Rules()).run(
        Work.GIT, "repo", 'echo "${GIT_DIR-unset}"', tree, log, 30
    )
    assert read(log) == "unset\n"


async def test_a_pinned_node_comes_first_on_the_path_of_an_unsandboxed_command(
    tmp_path: Path, tree: Path, bin_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = tmp_path / "home" / ".nvm" / "versions" / "node" / "v22.1.0" / "bin"
    node.mkdir(parents=True)
    for folder in (node, node.parent):
        folder.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    log = tmp_path / "run.log"
    await runner(tmp_path, Policy(sandbox=False, nvmrc_text="v22.1.0\n"), Rules()).run(
        Work.SETUP, "repo", 'echo "$PATH"', tree, log, 30
    )
    assert read(log) == f"{node}:{bin_folder}\n"


async def test_a_command_past_its_limit_gives_none(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    del bin_folder
    started = time.monotonic()
    code = await runner(tmp_path, Policy(sandbox=False), Rules()).run(
        Work.CHECKS, "repo", "/bin/sleep 30", tree, tmp_path / "run.log", 0.4
    )
    assert code is None
    assert time.monotonic() - started < 10


@pytest.mark.parametrize(
    ("work", "asked", "settings_folder", "offline"),
    [
        (Work.CHECKS, ("tree", "repo", False), "checks", "1"),
        (Work.SETUP, ("tree", "repo", True), "hooks", "no"),
        (Work.TEARDOWN, ("tree", "repo", False), "hooks", "no"),
        (Work.GIT, ("git", "repo", None), "hooks", "no"),
        (Work.PREVIEW, ("preview", "repo", None), "hooks", "no"),
    ],
)
async def test_a_sandboxed_command_runs_in_srt_with_the_settings_of_its_work(  # noqa: PLR0913, PLR0917
    tmp_path: Path,
    tree: Path,
    bin_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
    work: Work,
    asked: tuple[str, str, bool | None],
    settings_folder: str,
    offline: str,
) -> None:
    install_srt(bin_folder)
    monkeypatch.setenv("SECRET", "leaks")
    monkeypatch.setenv("HOME", "/home/someone")
    rules, log = Rules(), tmp_path / "run.log"
    command = (
        'echo "${SECRET-unset}|$HOME|$PATH|$CLAUDE_CODE_TMPDIR|$XDG_RUNTIME_DIR|'
        '${CODE_FACTORY_OFFLINE-no}"'
    )
    code = await runner(tmp_path, Policy(), rules).run(work, "repo", command, tree, log, 30)
    assert code == 0
    temporary = rules.seen_temporary[0]
    assert rules.asked == [asked]
    assert temporary.name.startswith("code-factory-tmp-")
    settings_file, shown = read(log).split("\n", 1)
    assert settings_file.startswith(f"{tmp_path / 'state' / settings_folder}/")
    assert settings_file.endswith(".sandbox.json")
    assert shown == (
        f"{SETTINGS}unset|/home/someone|{bin_folder}|{temporary}|{temporary}|{offline}\n"
    )
    assert not exists(temporary)
    assert entries(tmp_path / "state" / settings_folder) == []


async def test_the_command_reaches_srt_as_one_argument_whatever_it_holds(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    install_srt(bin_folder)
    log = tmp_path / "run.log"
    command = "printf '%s|' \"a b\" 'it'\"'\"'s' $(echo $((1+2)))"
    await runner(tmp_path, Policy(), Rules()).run(Work.CHECKS, "repo", command, tree, log, 30)
    assert read(log).split("\n", 1)[1] == f"{SETTINGS}a b|it's|3|"


async def test_without_srt_nothing_runs_and_the_log_says_how_to_go_on(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    del bin_folder
    log = tmp_path / "logs" / "run.log"
    marker = tmp_path / "ran"
    code = await runner(tmp_path, Policy(), Rules()).run(
        Work.CHECKS, "repo", f"touch {marker}", tree, log, 30
    )
    assert code == -1
    assert read(log) == (
        "the checks run inside srt (@anthropic-ai/sandbox-runtime), which is not installed; "
        "install it, or set [agents] sandbox = false in .code-factory/config.toml\n"
    )
    assert not exists(marker)


@pytest.mark.parametrize(
    ("work", "subject"),
    [
        (Work.SETUP, "the worktree hooks run"),
        (Work.TEARDOWN, "the worktree hooks run"),
        (Work.GIT, "the board's git in a run's clone runs"),
        (Work.PREVIEW, "the preview runs"),
    ],
)
async def test_the_missing_srt_sentence_names_what_could_not_run(
    tmp_path: Path, tree: Path, bin_folder: Path, work: Work, subject: str
) -> None:
    del bin_folder
    log = tmp_path / "run.log"
    await runner(tmp_path, Policy(), Rules()).run(work, "repo", "true", tree, log, 30)
    assert read(log).startswith(f"{subject} inside srt (@anthropic-ai/sandbox-runtime)")


async def test_settings_the_port_refuses_stop_the_run_with_the_ports_sentence(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    install_srt(bin_folder)
    log, marker = tmp_path / "run.log", tmp_path / "ran"
    rules = Rules(refusal="a connection key cannot be named: set it in the agents config")
    code = await runner(tmp_path, Policy(), rules).run(
        Work.CHECKS, "repo", f"touch {marker}", tree, log, 30
    )
    assert code == -1
    assert read(log) == "a connection key cannot be named: set it in the agents config\n"
    assert not exists(marker)
    assert not exists(rules.seen_temporary[0])


async def test_without_a_trusted_path_folder_the_child_gets_no_empty_path(
    tmp_path: Path, tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "relative")
    log = tmp_path / "run.log"
    await runner(tmp_path, Policy(sandbox=False), Rules()).run(
        Work.CHECKS, "repo", 'echo "$PATH"', tree, log, 30
    )
    assert read(log) == "/var/empty\n"


async def test_settings_that_cannot_be_written_are_a_refusal_in_the_log(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    install_srt(bin_folder)
    (tmp_path / "state").write_text("a file where the folder should be")
    log, marker = tmp_path / "run.log", tmp_path / "ran"
    code = await runner(tmp_path, Policy(), Rules()).run(
        Work.CHECKS, "repo", f"touch {marker}", tree, log, 30
    )
    assert code == -1
    assert read(log).startswith(
        f"the sandbox settings cannot be written in {tmp_path / 'state' / 'checks'}: "
    )
    assert not exists(marker)


async def test_an_unsandboxed_command_gets_only_the_base_variables(
    tmp_path: Path, tree: Path, bin_folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del bin_folder
    monkeypatch.setenv("CODE_FACTORY_DATABASE_URL", "postgresql://u:hunter2@h/x")
    monkeypatch.setenv("HOME", "/home/someone")
    log = tmp_path / "run.log"
    await runner(tmp_path, Policy(sandbox=False), Rules()).run(
        Work.CHECKS, "repo", 'echo "${CODE_FACTORY_DATABASE_URL-unset}|$HOME"', tree, log, 30
    )
    assert read(log) == "unset|/home/someone\n"


@pytest.mark.parametrize("work", [Work.CHECKS, Work.SETUP, Work.TEARDOWN, Work.GIT])
async def test_a_run_without_a_limit_is_refused_unless_it_is_a_preview(
    tmp_path: Path, tree: Path, bin_folder: Path, work: Work
) -> None:
    del bin_folder
    contained = runner(tmp_path, Policy(sandbox=False), Rules())
    with pytest.raises(ValueError, match=f"a {work.value} run needs a time limit"):
        await contained.run(work, "repo", "true", tree, tmp_path / "run.log", None)


async def test_a_preview_may_run_without_a_limit(
    tmp_path: Path, tree: Path, bin_folder: Path
) -> None:
    del bin_folder
    contained = runner(tmp_path, Policy(sandbox=False), Rules())
    assert (
        await contained.run(Work.PREVIEW, "repo", "exit 0", tree, tmp_path / "run.log", None) == 0
    )

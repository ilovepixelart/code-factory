"""The run wrapper as a real process: it records the agent's exit and survives the group's stop."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest

from code_factory.runs.adapters.runner import wrapper

WRAPPER = [sys.executable, "-m", "code_factory.runs.adapters.runner"]
ENV = {"PATH": "/usr/bin:/bin", "PYTHONPATH": os.pathsep.join(sys.path)}


async def run_wrapper(
    tmp_path: Path,
    *command: str,
    extra: dict[str, str] | None = None,
    timeout_args: tuple[str, ...] = (),
) -> tuple[asyncio.subprocess.Process, Path, Path]:
    exit_file, log = tmp_path / "ab12cd34ef56.exit", tmp_path / "run.log"
    with log.open("wb") as sink:
        process = await asyncio.create_subprocess_exec(
            *WRAPPER,
            str(exit_file),
            *timeout_args,
            "--",
            *command,
            env=ENV | {wrapper.RUNS_VARIABLE: str(tmp_path)} | (extra or {}),
            cwd=tmp_path,
            stdout=sink,
            stderr=sink,
            stdin=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    return process, exit_file, log


async def test_deadline_ends_the_group_even_without_a_board_to_collect(tmp_path: Path) -> None:
    process, exit_file, log = await run_wrapper(
        tmp_path,
        "sh",
        "-c",
        "sleep 2 && touch escaped & wait",
        timeout_args=("--timeout-seconds", "1"),
    )
    assert await asyncio.wait_for(process.wait(), 5) == -signal.SIGKILL
    assert int(exit_file.read_text()) < -255
    assert "1 second" in log.read_text()
    await asyncio.sleep(1.1)
    assert not (tmp_path / "escaped").exists()


async def test_a_plain_run_records_the_agents_exit_and_copies_its_output(tmp_path: Path) -> None:
    process, exit_file, log = await run_wrapper(
        tmp_path, "sh", "-c", "echo out; echo err >&2; exit 3"
    )
    assert await asyncio.wait_for(process.wait(), 30) == 3
    assert exit_file.read_text().strip() == "3"
    assert sorted(log.read_text().split()) == ["err", "out"]


async def test_a_program_that_cannot_be_found_is_127_and_says_so(tmp_path: Path) -> None:
    process, exit_file, log = await run_wrapper(tmp_path, "no-such-agent-program")
    assert await asyncio.wait_for(process.wait(), 30) == 127
    assert exit_file.read_text().strip() == "127"
    assert "no-such-agent-program" in log.read_text()


async def test_a_program_is_found_on_absolute_path_folders_only(tmp_path: Path) -> None:
    (tmp_path / "planted").write_text("#!/bin/sh\necho planted\n")
    (tmp_path / "planted").chmod(0o755)
    process, _, log = await run_wrapper(tmp_path, "planted", extra={"PATH": ".:./sub:/usr/bin"})
    assert await asyncio.wait_for(process.wait(), 30) == 127
    assert "planted" not in log.read_text().splitlines()


async def test_the_group_s_sigterm_ends_the_agent_not_the_wrapper_which_records_it(
    tmp_path: Path,
) -> None:
    process, exit_file, _ = await run_wrapper(tmp_path, "sleep", "30")
    for _ in range(100):  # the wrapper has installed its handler once its agent runs
        await asyncio.sleep(0.1)
        if await _child_count(process.pid):
            break
    os.killpg(process.pid, signal.SIGTERM)
    assert await asyncio.wait_for(process.wait(), 30) == 143
    assert exit_file.read_text().strip() == "-15"


async def _child_count(pid: int) -> int:
    done = await asyncio.create_subprocess_exec(
        "/usr/bin/pgrep", "-P", str(pid), stdout=asyncio.subprocess.PIPE
    )
    out, _ = await done.communicate()
    return len(out.split())


async def test_a_key_is_replaced_even_when_the_agent_prints_it_in_two_writes(
    tmp_path: Path,
) -> None:
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"patterns": [["sk-very-secret-key", "[redacted key]"]]}))
    script = "printf 'before sk-very-'; sleep 0.3; printf 'secret-key after\\n'"
    process, _, log = await run_wrapper(
        tmp_path, "sh", "-c", script, extra={"CODE_FACTORY_OWNER_CONTEXT": str(context)}
    )
    assert await asyncio.wait_for(process.wait(), 30) == 0
    assert log.read_text() == "before [redacted key] after\n"


async def test_an_owner_context_that_cannot_be_read_stops_the_run_before_it_starts(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "started"
    process, exit_file, log = await run_wrapper(
        tmp_path,
        "sh",
        "-c",
        f"touch {marker}",
        extra={"CODE_FACTORY_OWNER_CONTEXT": str(tmp_path / "missing.json")},
    )
    assert await asyncio.wait_for(process.wait(), 30) == 1
    assert not marker.exists()
    assert exit_file.read_text().strip() == "1"
    assert "owner context" in log.read_text()


@pytest.mark.parametrize("argv", [[], ["x.exit"], ["x.exit", "--"], ["x.exit", "claude"]])
async def test_a_command_line_without_an_exit_file_and_a_command_is_refused(
    tmp_path: Path, argv: list[str]
) -> None:
    process = await asyncio.create_subprocess_exec(
        *WRAPPER,
        *argv,
        cwd=tmp_path,
        env=ENV,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await asyncio.wait_for(process.communicate(), 30)
    assert process.returncode == 2
    assert b"usage" in out


async def test_a_stop_that_arrived_before_the_agent_started_means_the_agent_never_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wrapper, "_stop_requested", True)
    marker = tmp_path / "started"
    code = await wrapper.run(tmp_path / "ab.exit", ["/bin/sh", "-c", f"touch {marker}"])
    assert code == -signal.SIGTERM
    assert not marker.exists()
    assert (tmp_path / "ab.exit").read_text().strip() == "-15"


def test_the_exit_code_is_written_to_a_temporary_file_and_renamed_into_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "ab.exit"
    seen: list[bool] = []
    original = Path.replace

    def spy(self: Path, destination: Path) -> Path:
        seen.append(Path(destination).exists())
        return original(self, destination)

    monkeypatch.setattr(Path, "replace", spy)
    wrapper.record_exit(target, 7)
    assert seen == [False]
    assert target.read_text().strip() == "7"


async def test_an_agent_whose_output_cannot_be_copied_is_stopped_not_left_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "pid"

    async def broken_copy(*_args: object) -> None:
        for _ in range(100):  # the agent is running once it has written its pid
            if pid_file.exists() and pid_file.read_text().strip():
                break
            await asyncio.sleep(0.05)
        raise OSError("stdout is gone")

    monkeypatch.setattr(wrapper, "_copy", broken_copy)

    with pytest.raises(OSError, match="stdout is gone"):
        await wrapper.run(
            tmp_path / "ab.exit", ["/bin/sh", "-c", f"echo $$ > {pid_file}; exec sleep 30"]
        )

    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def _entries(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir())


@pytest.mark.parametrize(
    "exit_file",
    [
        "ab12cd34ef56.exit",  # relative
        "{tmp}/notes.txt",
        "{tmp}/AB12CD34EF56.exit",
        "{tmp}/ab12cd34ef5.exit",
        "{tmp}/sub/../ab12cd34ef56.exit",
        "{tmp}/sub/ab12cd34ef56.exit",  # below the runs folder, not in it
    ],
)
async def test_an_exit_file_the_board_would_not_name_is_refused_before_anything_starts(
    tmp_path: Path, exit_file: str
) -> None:
    marker = tmp_path / "started"
    named = exit_file.format(tmp=tmp_path)
    process = await asyncio.create_subprocess_exec(
        *WRAPPER, named, "--", "/bin/sh", "-c", f"touch {marker}",
        cwd=tmp_path, env=ENV | {wrapper.RUNS_VARIABLE: str(tmp_path)},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )  # fmt: skip
    out, _ = await asyncio.wait_for(process.communicate(), 30)

    assert (process.returncode, out.decode()) == (
        2,
        (
            "the exit file must be an absolute path to <12 hex digits>.exit in the folder "
            f"CODE_FACTORY_RUNS_DIR names, not {named}\n"
        ),
    )
    assert _entries(tmp_path) == []  # nothing started, no exit file written


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("/runs/ab12cd34ef56.exit", True),
        ("/runs/0123456789ab.exit", True),
        ("/a/b/0123456789ab.exit", False),  # another folder
        ("/runs/sub/0123456789ab.exit", False),  # below the runs folder
        ("/runsx/0123456789ab.exit", False),  # a folder that only starts like it
        ("ab12cd34ef56.exit", False),
        ("/runs/ab12cd34ef56.log", False),
        ("/runs/ab12cd34ef56.exit.tmp", False),
        ("/runs/../ab12cd34ef56.exit", False),
    ],
)
def test_the_exit_file_is_one_the_board_would_name(text: str, *, named: bool) -> None:
    assert (wrapper.exit_file(text, "/runs") == Path(text)) is named
    assert (wrapper.exit_file(text, "/runs") is None) is not named


@pytest.mark.parametrize("runs", [None, ""])
def test_an_exit_file_is_refused_when_no_runs_folder_is_named(runs: str | None) -> None:
    assert wrapper.exit_file("/runs/ab12cd34ef56.exit", runs) is None


def test_a_link_in_the_runs_folder_cannot_lead_the_exit_file_out_of_it(tmp_path: Path) -> None:
    runs, outside = tmp_path / "runs", tmp_path / "outside"
    runs.mkdir()
    outside.mkdir()
    (runs / "ab12cd34ef56.exit").symlink_to(outside / "ab12cd34ef56.exit")

    assert wrapper.exit_file(str(runs / "ab12cd34ef56.exit"), str(runs)) is None


def test_an_exit_file_in_a_runs_folder_reached_through_a_link_is_its_resolved_path(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "linked").symlink_to(real)

    named = wrapper.exit_file(str(tmp_path / "linked" / "ab12cd34ef56.exit"), str(real))

    assert named == real.resolve() / "ab12cd34ef56.exit"


def test_main_refuses_an_exit_file_the_board_would_not_name_in_process(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert wrapper.main(["notes.txt", "--", "/bin/true"]) == wrapper.USAGE_STATUS
    assert capsys.readouterr().err == (
        "the exit file must be an absolute path to <12 hex digits>.exit in the folder "
        "CODE_FACTORY_RUNS_DIR names, not notes.txt\n"
    )


def test_main_runs_the_command_and_records_its_exit_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handlers: list[int] = []
    # The test process keeps its own SIGTERM handling; the wrapper's handler is only recorded.
    monkeypatch.setattr(wrapper.signal, "signal", lambda number, _handler: handlers.append(number))
    exit_path = tmp_path / "ab12cd34ef56.exit"
    monkeypatch.setenv(wrapper.RUNS_VARIABLE, str(tmp_path))
    seen = tmp_path / "seen"
    script = f'printf %s "${{{wrapper.RUNS_VARIABLE}-unset}}" > {seen}; exit 3'

    assert wrapper.main([str(exit_path), "--", "/bin/sh", "-c", script]) == 3

    assert exit_path.read_text() == "3\n"
    assert seen.read_text() == "unset"  # the agent does not inherit the runs folder
    assert handlers[0] == signal.SIGTERM  # asyncio.run adds its own SIGINT handler after it

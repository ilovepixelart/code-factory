import ast
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from sessions_values import golden

from code_factory.platform.text import masked
from code_factory.sessions.rules import capture

SCRIPT = Path(capture.__file__)


def run_hook(payload: bytes, state: Path, **env: str) -> subprocess.CompletedProcess[bytes]:
    environment = {"CODE_FACTORY_STATE_DIR": str(state), "HOME": str(state), **env}
    return subprocess.run(  # noqa: S603  # our own interpreter and file
        [sys.executable, "-I", "-S", str(SCRIPT)],
        input=payload,
        env=environment,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_the_hook_appends_one_line_prints_nothing_and_exits_zero(tmp_path: Path) -> None:
    done = run_hook(b'{"session_id": "s-1", "hook_event_name": "Stop"}', tmp_path)
    spool = tmp_path / "spool" / "s-1.jsonl"
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    lines = spool.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["hook_event_name"] == "Stop"
    assert stat.S_IMODE(spool.stat().st_mode) == 0o600


def test_a_session_that_reports_twice_has_two_lines(tmp_path: Path) -> None:
    run_hook(b'{"session_id": "s-1", "n": 1}', tmp_path)
    run_hook(b'{"session_id": "s-1", "n": 2}', tmp_path)
    lines = (tmp_path / "spool" / "s-1.jsonl").read_text().splitlines()
    assert [json.loads(line)["n"] for line in lines] == [1, 2]


def failures(state: Path) -> list[dict[str, str]]:
    log = state / "capture-errors.log"
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_invalid_json_is_logged_and_the_hook_stays_silent(tmp_path: Path) -> None:
    done = run_hook(b"not json", tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    (entry,) = failures(tmp_path)
    assert entry["reason"].startswith("JSONDecodeError:")
    assert entry["payload_head"] == "not json"
    assert not (tmp_path / "spool").exists()


def test_a_directory_in_place_of_the_spool_file_is_logged_not_raised(tmp_path: Path) -> None:
    (tmp_path / "spool" / "s-1.jsonl").mkdir(parents=True)
    done = run_hook(b'{"session_id": "s-1"}', tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    (entry,) = failures(tmp_path)
    assert entry["reason"].startswith("IsADirectoryError:")


def test_a_state_folder_that_is_a_file_leaves_nothing_to_log_and_still_exits_zero(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.write_text("a file")
    done = run_hook(b'{"session_id": "s-1"}', state)
    assert (done.returncode, done.stdout, done.stderr) == (0, b"", b"")
    assert state.read_text() == "a file"


def test_eight_processes_appending_large_lines_leave_whole_lines(tmp_path: Path) -> None:
    payload = json.dumps({"session_id": "big", "text": "é" * 1900, "more": ["x" * 1900] * 20})
    assert len(payload) > 40_000
    workers = [
        subprocess.Popen(  # noqa: S603  # our own interpreter and file
            [
                sys.executable,
                "-I",
                "-S",
                str(Path(__file__).with_name("append_worker.py")),
                str(SCRIPT),
                payload,
                str(tmp_path),
            ],
            env={},
        )
        for _ in range(8)
    ]
    assert [worker.wait(timeout=60) for worker in workers] == [0] * 8
    lines = (tmp_path / "spool" / "big.jsonl").read_bytes().splitlines()
    assert len(lines) == 200
    assert all(json.loads(line)["session_id"] == "big" for line in lines)


def test_the_hook_imports_only_the_standard_library_and_runs_without_an_environment(
    tmp_path: Path,
) -> None:
    imported = {
        name.split(".")[0]
        for node in ast.walk(ast.parse(SCRIPT.read_text()))
        for name in (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
    }
    assert imported <= set(sys.stdlib_module_names)
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-S", str(SCRIPT)],
        input=b'{"session_id": "s"}',
        env={"HOME": str(tmp_path)},
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert done.returncode == 0
    assert (tmp_path / ".local/state/code-factory/spool/s.jsonl").is_file()


MASKING_CASES = [
    *[case for case in golden("capture_cases.json") if "ecret" in case or "oken" in case],
    '{"authorization": "Bearer abc123"}',
    r"{\"token\":\"ab\\/cd\"}",
    "token=ab\\cd next",
    "password: 'ab\\'cd' next",
    r"{\\\"token\\\":\\\"ab\\\\/cd x\\\",\\\"n\\\":1}",
    "keys ghp_abcDEF123 gho_x xoxb-1-2 xoxp-3 and AKIAABCDEFGHIJKLMNOP end",
]


def test_the_hooks_secret_patterns_equal_the_platforms() -> None:
    assert [p.pattern for p in capture._PATTERNS] == [
        p.pattern
        for p in __import__("code_factory.platform.text.masking").platform.text.masking._PATTERNS
    ]


@pytest.mark.parametrize("text", MASKING_CASES)
def test_the_hook_masks_exactly_what_the_platform_masks(text: str) -> None:
    assert capture.mask(text) == masked(text)


def publish(state: Path, patterns: list[list[str]], references: list[str]) -> None:
    (state / "redaction.json").write_text(
        json.dumps({"references": references, "patterns": patterns}), encoding="utf-8"
    )


def test_a_run_whose_context_is_listed_has_it_replaced_in_the_spool(tmp_path: Path) -> None:
    publish(tmp_path, [["the owner secret", "[ctx]"]], ["agent@3"])
    run_hook(
        b'{"session_id": "s", "prompt": "Go. the owner secret"}',
        tmp_path,
        CODE_FACTORY_CONTEXT="agent@3",
    )
    line = json.loads((tmp_path / "spool" / "s.jsonl").read_text())
    assert line["prompt"] == "Go. [ctx]"


def test_a_run_naming_an_unlisted_context_keeps_nothing_and_logs_why(tmp_path: Path) -> None:
    publish(tmp_path, [["the owner secret", "[ctx]"]], ["agent@3"])
    done = run_hook(
        b'{"session_id": "s", "prompt": "the owner secret"}',
        tmp_path,
        CODE_FACTORY_CONTEXT="agent@2",
    )
    assert done.returncode == 0
    assert not (tmp_path / "spool").exists()
    (entry,) = failures(tmp_path)
    assert entry == {
        "at": entry["at"],
        "reason": "the owner's context agent@2 cannot be read",
        "payload_head": "",
    }


def test_a_run_naming_a_context_with_no_redaction_file_keeps_nothing(tmp_path: Path) -> None:
    run_hook(b'{"session_id": "s"}', tmp_path, CODE_FACTORY_CONTEXT="agent@1")
    assert not (tmp_path / "spool").exists()
    assert len(failures(tmp_path)) == 1


def test_no_context_and_no_file_records_the_payload_as_it_is(tmp_path: Path) -> None:
    run_hook(b'{"session_id": "s", "prompt": "plain"}', tmp_path)
    assert json.loads((tmp_path / "spool" / "s.jsonl").read_text())["prompt"] == "plain"


def test_the_environment_of_a_test_does_not_leak_a_context(tmp_path: Path) -> None:
    assert "CODE_FACTORY_CONTEXT" not in os.environ
    run_hook(b'{"session_id": "s"}', tmp_path)
    assert (tmp_path / "spool" / "s.jsonl").is_file()


def test_a_payload_that_fails_is_logged_without_its_secrets_or_the_owner_context(
    tmp_path: Path,
) -> None:
    publish(tmp_path, [["the owner secret", "[ctx]"]], ["agent@3"])
    run_hook(
        b'password=hunter2 the owner secret {"not": json',
        tmp_path,
        CODE_FACTORY_CONTEXT="agent@3",
    )
    (entry,) = failures(tmp_path)
    assert "hunter2" not in entry["payload_head"]
    assert "the owner secret" not in entry["payload_head"]
    assert entry["payload_head"].startswith("password=[redacted] [ctx] ")

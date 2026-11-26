import os
import subprocess
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[2] / "scripts" / "gate.sh"


@pytest.mark.parametrize(
    "name",
    [
        "code_factory",
        "postgres",
        "x?host=evil_test",
        "a b_test",
        "Code_test",
        "code_factory/x_test",
    ],
)
def test_the_gate_refuses_a_test_database_name_that_is_not_plain(name: str) -> None:
    result = subprocess.run(  # noqa: S603  # the gate is this repository's own script
        ["/bin/sh", str(GATE)],
        env={**os.environ, "CODE_FACTORY_TEST_DATABASE": name},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr.strip() == (
        "gate: CODE_FACTORY_TEST_DATABASE must match [a-z0-9_]+_test (lowercase letters, "
        "digits and underscores, ending in _test)"
    )


def _fake(directory: Path, name: str, body: str) -> None:
    script = directory / name
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://localhost/code_factory",
        "postgresql+asyncpg://other.example/code_factory_test",
        "postgresql+asyncpg://localhost/code_factory_test?database=code_factory",
    ],
)
def test_the_gate_rejects_unsafe_runner_urls_before_checking_the_database(
    tmp_path: Path, url: str
) -> None:
    accessed = tmp_path / "keychain-accessed"
    _fake(tmp_path, "security", f"touch '{accessed}'; exit 1")
    result = subprocess.run(  # noqa: S603  # the gate and test URL are local fixture inputs
        ["/bin/sh", str(GATE), "--base", "HEAD"],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CODE_FACTORY_GATE_DATABASE_URL": url,
            "UV_NO_CACHE": "1",
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 1
    assert "refusing to run tests" in result.stderr
    assert not accessed.exists()


@pytest.mark.parametrize("runner_url", ["", "postgresql+asyncpg://localhost/code_factory_test"])
def test_the_gate_does_not_hand_the_database_url_to_the_web_steps(
    tmp_path: Path, runner_url: str
) -> None:
    """The URL holds the password; the web steps (pnpm, vite, node) never need it."""
    seen = tmp_path / "seen"
    _fake(tmp_path, "security", "echo fake-password")
    _fake(tmp_path, "uv", f'echo "uv ${{CODE_FACTORY_DATABASE_URL:+set}}" >> {seen}')
    _fake(
        tmp_path,
        "pnpm",
        f'echo "pnpm ${{CODE_FACTORY_DATABASE_URL:+set}}'
        f'${{CODE_FACTORY_GATE_DATABASE_URL:+set}}" >> {seen}',
    )
    result = subprocess.run(  # noqa: S603  # the gate is this repository's own script
        ["/bin/sh", str(GATE)],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CODE_FACTORY_TEST_DATABASE": "code_factory_gate_probe_test",
            "CODE_FACTORY_DATABASE_URL": "",
            "CODE_FACTORY_GATE_DATABASE_URL": runner_url,
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = seen.read_text(encoding="utf-8").splitlines()
    assert "uv set" in lines
    pnpm_lines = [line for line in lines if line.startswith("pnpm")]
    assert pnpm_lines
    assert set(pnpm_lines) == {"pnpm "}


@pytest.mark.parametrize(
    ("selected", "pytest_args"),
    [
        ("", None),
        ("vue", None),
        ("python tests/runs/test_example.py", "pytest --no-cov tests/runs/test_example.py"),
        ("python tests/runs", "pytest --no-cov -n 3 --dist worksteal tests/runs"),
    ],
)
def test_fast_gate_only_prepares_the_database_for_selected_python_tests(
    tmp_path: Path, selected: str, pytest_args: str | None
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    gate = scripts / GATE.name
    gate.write_bytes(GATE.read_bytes())
    tools = tmp_path / "bin"
    tools.mkdir()
    seen = tmp_path / "seen"
    _fake(tools, "security", f'echo "database" >> "{seen}"\necho fake-password')
    _fake(tools, "pnpm", f'echo "pnpm $*" >> "{seen}"')
    _fake(tools, "gitleaks", "exit 0")
    _fake(
        tools,
        "uv",
        f"""
printf '%s\\n' "$*" >> "{seen}"
case "$*" in
  *"gate_delta.py base") echo base ;;
  *"gate_delta.py affected"*) printf '%s\\n' "{selected}" ;;
esac
""",
    )
    result = subprocess.run(  # noqa: S603  # the gate and its fake commands are local fixtures
        ["/bin/sh", str(gate), "--fast", "--secrets"],
        env={
            **os.environ,
            "PATH": f"{tools}:{os.environ['PATH']}",
            "CODE_FACTORY_GATE_DATABASE_URL": "",
            "CODE_FACTORY_TEST_DATABASE": "code_factory_gate_probe_test",
            "CODE_FACTORY_FAST_TEST_WORKERS": "3",
        },
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    lines = seen.read_text(encoding="utf-8").splitlines()
    assert "run --no-sync python scripts/gate_scan.py gitleaks base" in lines
    assert ("database" in lines) == (pytest_args is not None)
    if pytest_args is not None:
        assert f"run --no-sync {pytest_args}" in lines
    if selected == "vue":
        assert any("exec vitest run" in line for line in lines)

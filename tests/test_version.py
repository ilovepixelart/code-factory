import tomllib
from importlib.metadata import version

import pytest

import code_factory
from code_factory.app import MCP_TOKEN_VARIABLE, create_app, create_mcp_server
from code_factory.platform.config import Settings
from repo_files import ROOT

PYPROJECT = ROOT / "pyproject.toml"


def test_one_version_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MCP_TOKEN_VARIABLE, "cfo_" + "A" * 43)
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    settings = Settings(database_url="postgresql+asyncpg://u:p@h:1/x_test", _env_file=None)
    assert code_factory.__version__ == declared
    assert version("code-factory") == declared
    assert create_app(settings, guarded=False).openapi()["info"]["version"] == declared
    assert create_mcp_server(settings).version == declared


def test_the_public_exports_are_listed() -> None:
    assert sorted(code_factory.__all__) == ["PACKAGE_NAME", "__version__"]


def test_uv_is_pinned_to_its_managed_python() -> None:
    uv = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["uv"]
    assert uv["python-preference"] == "only-managed"

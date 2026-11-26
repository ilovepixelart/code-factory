"""The code on the landing page is code the board accepts.

A landing page is read as a promise. Every snippet it shows lives in `site/web/snippets.toml`;
these tests hold each one to the thing that decides it: an MCP call to the tool listings pinned
in `tests/golden/mcp/`, a command line to the real `code-factory` parser, a config.toml to the
rules `code-factory config check` applies.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import tomllib
import webbrowser
from typing import Any

import pytest

from code_factory.app import MODULES, create_app, create_mcp_server, open_services
from code_factory.platform import cli
from code_factory.push.rules import address_refusal
from code_factory.settings.rules.config import findings
from code_factory.stages.models import RELEASED, Stage
from repo_files import PROJECT_VERSION, ROOT

SITE = ROOT / "site"
SNIPPETS_FILE = SITE / "web" / "snippets.toml"
INDEX = SITE / "web" / "templates" / "index.html"
TOOLS = ROOT / "tests" / "golden" / "mcp"
WEB_SCRIPTS = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))["scripts"]

_ALL = tomllib.loads(SNIPPETS_FILE.read_text(encoding="utf-8"))
SNIPPETS: dict[str, dict[str, str]] = {
    f"{group}.{key}": entry for group in ("panes", "examples") for key, entry in _ALL[group].items()
}


def _of(lang: str) -> list[str]:
    return sorted(name for name, entry in SNIPPETS.items() if entry["lang"] == lang)


def _tool_schemas() -> dict[str, dict[str, Any]]:
    """Each tool's input schema, from every caller's pinned listing."""
    schemas: dict[str, dict[str, Any]] = {}
    for listing in sorted(TOOLS.glob("tools.*.json")):
        for tool in json.loads(listing.read_text(encoding="utf-8")):
            schemas[tool["name"]] = tool["inputSchema"]
    return schemas


def _parser() -> argparse.ArgumentParser:
    return cli._parser(create_app, create_mcp_server, open_services, MODULES, webbrowser.open)


def _command_lines(source: str) -> list[list[str]]:
    """Each line that runs something, as words, without its comment."""
    lines = (shlex.split(line, comments=True) for line in source.splitlines())
    return [words[2:] if words[:2] == ["uv", "run"] else words for words in lines if words]


def test_the_snippet_file_has_panes_and_examples_in_every_language() -> None:
    assert {entry["lang"] for entry in SNIPPETS.values()} == {"mcp", "shell", "toml"}
    assert len(_ALL["examples"]) >= 6


@pytest.mark.parametrize("name", _of("mcp"))
def test_every_mcp_call_names_a_tool_the_board_serves_with_arguments_it_accepts(
    name: str,
) -> None:
    request = json.loads(SNIPPETS[name]["source"])
    assert request["method"] == "tools/call"
    schema = _tool_schemas().get(request["params"]["name"])
    assert schema is not None, f"{name}: no tool {request['params']['name']}"
    arguments = request["params"]["arguments"]
    properties = schema["properties"]
    assert set(arguments) <= set(properties), f"{name}: {set(arguments) - set(properties)}"
    assert set(schema.get("required", [])) <= set(arguments), f"{name}: a required one is missing"
    for key, value in arguments.items():
        allowed = properties[key].get("enum")
        assert allowed is None or value in allowed, f"{name}: {key}={value!r} not in {allowed}"


def test_a_choice_in_a_question_has_only_the_fields_a_choice_has() -> None:
    choice = _tool_schemas()["ask_question"]["properties"]["choices"]["anyOf"][0]["items"]
    for name in _of("mcp"):
        arguments = json.loads(SNIPPETS[name]["source"])["params"]["arguments"]
        for picked in arguments.get("choices") or []:
            if isinstance(picked, dict):
                assert set(picked) <= set(choice["properties"]), f"{name}: {picked}"


def test_every_path_a_lesson_cites_exists() -> None:
    cited = [
        path
        for name in _of("mcp")
        for path in json.loads(SNIPPETS[name]["source"])["params"]["arguments"].get("cites", [])
    ]
    assert cited
    assert [path for path in cited if not (ROOT / path).exists()] == []


@pytest.mark.parametrize("name", _of("shell"))
def test_every_command_line_is_one_the_tools_accept(name: str) -> None:
    parser = _parser()
    for words in _command_lines(SNIPPETS[name]["source"]):
        match words:
            case ["code-factory", *rest]:
                parser.parse_args(rest)  # argparse exits 2 on a line it refuses
            case ["uv", "sync"]:
                pass
            case ["sh", script, *options]:
                assert (ROOT / script).is_file(), f"{name}: there is no {script}"
                assert not options or (script == "scripts/start.sh" and options == ["--local"]), (
                    f"{name}: unknown arguments for {script}: {options}"
                )
            case ["pnpm", "--dir", "web", "install", *_]:
                pass
            case ["pnpm", "--dir", "web", script]:
                assert script in WEB_SCRIPTS, f"{name}: web/package.json has no {script}"
            case _:
                pytest.fail(f"{name}: no check knows the line {words}")


def test_a_refused_command_line_fails_the_check() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["stage", "summon", "CF-1"])


def test_the_push_address_is_one_the_board_takes() -> None:
    lines = [w for n in _of("shell") for w in _command_lines(SNIPPETS[n]["source"])]
    pushes = [words[2:] for words in lines if words[:2] == ["code-factory", "push"]]
    assert pushes
    for format_, address in pushes:
        assert address_refusal(format_, address) is None


@pytest.mark.parametrize("name", _of("toml"))
def test_every_config_is_one_config_check_passes(name: str) -> None:
    text = SNIPPETS[name]["source"]
    assert findings(tomllib.loads(text), text) == []


def test_a_config_with_an_unknown_key_has_a_finding() -> None:
    text = '[checks]\ncommand = "make"\nretry = 3\n'
    assert [f.message for f in findings(tomllib.loads(text), text)] == [
        "checks.retry: unknown field"
    ]


def test_the_columns_on_the_page_are_the_stages_the_board_has() -> None:
    listed = re.findall(r"\('([a-z]+)', 'bg-chart-\d', '", INDEX.read_text(encoding="utf-8"))
    assert listed == [*(stage.value for stage in Stage), RELEASED]


def test_the_templates_carry_no_version_of_their_own() -> None:
    templates = sorted((SITE / "web" / "templates").rglob("*.html"))
    assert templates
    pinned = [t.name for t in templates if PROJECT_VERSION in t.read_text(encoding="utf-8")]
    assert pinned == []


def _collected(request: pytest.FixtureRequest) -> int:
    """The suite's test count: this session's own when it collected the whole suite."""
    if not request.config.args or request.config.args == [str(ROOT / "tests")]:
        return len(request.session.items)
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov", "-p", "no:xdist"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=25,
    ).stdout
    total = re.search(r"(\d+) tests collected", out)
    assert total, f"could not read the count from: {out[-200:]}"
    return int(total.group(1))


def test_the_test_count_on_the_page_is_the_real_one(request: pytest.FixtureRequest) -> None:
    claimed = re.search(r"\('Tests', '([\d,]+)\+", INDEX.read_text(encoding="utf-8"))
    assert claimed, "the page no longer states a test count"
    actual, floor = _collected(request), int(claimed.group(1).replace(",", ""))
    # A floor, not an exact count: every new test would otherwise edit the page.
    assert floor <= actual < floor + 500, f"the page claims {floor}+, pytest collects {actual}"

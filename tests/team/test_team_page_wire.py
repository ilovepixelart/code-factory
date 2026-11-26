"""The Team page's answer as the web app reads it: its golden, and its keys against the web
app's own types (`web/src/lib/teamNow.ts`, `web/src/generated/Doing.ts` and `Last.ts`).

A change to the golden is read by a person before it is committed: regenerate it with
`CODE_FACTORY_BLESS=1` and look at the diff.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

from code_factory.team.models import Doing, Last, Usage
from code_factory.team.rules import assemble
from repo_files import ROOT
from team_page_values import (
    HOUR,
    MINUTE,
    NOW,
    PULL,
    TODAY,
    activity,
    facts,
    owner,
    ticket,
    worker,
)

GOLDEN = ROOT / "tests" / "golden" / "team" / "now.json"
TEAM_NOW_TS = (ROOT / "web" / "src" / "lib" / "teamNow.ts").read_text(encoding="utf-8")
GENERATED = ROOT / "web" / "src" / "generated"


def the_page() -> dict[str, Any]:
    """The hand-built page: one row of each group, a second line, a pull request, a peek."""
    questions = ticket(
        "CF-1", "build", activities=(activity(NOW - 3 * HOUR, "created", type="bug"),)
    )
    review = ticket(
        "CF-2",
        "review",
        first_commit=NOW - 100 * MINUTE,
        pull=(f"{PULL}20", "open"),
        activities=(
            activity(NOW - 2 * HOUR, "created"),
            activity(NOW - 90 * MINUTE, "checks", exit_code=1, words="Checks failed"),
            activity(
                NOW - 30 * MINUTE,
                "pull_request",
                url=f"{PULL}20",
                words=f"Pull request opened ({PULL}20)",
            ),
        ),
        check=False,
    )
    merged = ticket(
        "CF-4",
        "merged",
        first_commit=TODAY + 10 * MINUTE,
        merged=NOW - HOUR,
        activities=(activity(TODAY, "created"),),
    )
    page = assemble(
        facts(
            [questions, review, ticket("CF-3", "build"), merged, ticket("CF-5", "build")],
            [
                worker("CF-3", "agent", "builder", "build run", NOW - 70 * MINUTE),
                worker("CF-1", "gate", "gate", "rust-test", NOW - 5 * MINUTE),
                worker(
                    "CF-5",
                    "session",
                    "ticket-worker 7c2e",
                    "Read a.rs",
                    NOW - HOUR,
                    last_event=NOW - 20 * MINUTE,
                ),
            ],
            [owner("CF-1", "questions", "", NOW - 47 * MINUTE, count=3)],
            paused=("writer",),
        )
    )
    return page.model_dump(by_alias=True, mode="json")


def test_the_page_answer_is_its_golden() -> None:
    answer = json.dumps(the_page(), indent=2) + "\n"
    if os.environ.get("CODE_FACTORY_BLESS") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(answer, encoding="utf-8")
    assert answer == GOLDEN.read_text(encoding="utf-8")


def fields(source: str) -> list[str]:
    """The names of the fields written at the top level of an interface or object type body."""
    return [str(name) for name in re.findall(r"^  (\w+)\??:", source, flags=re.MULTILINE)]


def interface(name: str) -> str:
    """The body of `interface <name> { ... }` in the web app's types."""
    found = re.search(rf"interface {name} \{{\n(.*?)\n\}}", TEAM_NOW_TS, flags=re.DOTALL)
    assert found, name
    return str(found.group(1))


def inline(field: str) -> list[str]:
    """The keys of an inline object type such as `ticket: { repository: string; ... }`."""
    found = re.search(rf"{field}: \{{([^}}]*)\}}", TEAM_NOW_TS)
    assert found, field
    return [str(name) for name in re.findall(r"(\w+)\??:", found.group(1))]


def test_the_page_has_the_keys_the_web_app_reads_in_the_order_it_lists_them() -> None:
    page = the_page()
    row = page["groups"]["needs_you"][0]
    assert list(page) == fields(f"\n{interface('TeamNow')}")
    assert list(row) == fields(f"\n{interface('TeamRow')}")
    assert list(page["stages"][0]) == fields(f"\n{interface('StageTimes')}")
    assert list(page["stages"][0]["today"]) == fields(f"\n{interface('Median')}")
    assert list(next(iter(page["peek"].values()))) == fields(f"\n{interface('Peek')}")


def test_the_nested_objects_have_the_keys_the_web_app_reads() -> None:
    page = the_page()
    rows = [row for group in page["groups"].values() for row in group]
    with_pull = next(row for row in rows if row["pull"])
    peek = page["peek"]["sample/CF-2"]
    assert list(rows[0]["ticket"]) == inline("ticket")
    assert list(rows[0]["actor"]) == inline("actor")
    assert list(with_pull["pull"]) == ["number", "url", "gate", "merge"]
    assert list(page["cycle"]) == inline("cycle")
    assert list(peek["milestones"][0]) == inline("milestones")
    assert list(peek["events"][0]) == inline("events")


def test_a_second_line_has_the_keys_of_the_pick_the_web_app_names() -> None:
    page = the_page()
    row = next(row for group in page["groups"].values() for row in group if row["also"])
    picked = re.search(r"type Also = Pick<TeamRow, ([^>]*)>", TEAM_NOW_TS)
    assert picked
    assert list(row["also"][0]) == [str(n) for n in re.findall(r"'(\w+)'", picked.group(1))]


def test_the_groups_the_counts_and_the_stages_are_those_the_web_app_names() -> None:
    page = the_page()
    groups = re.search(r"type Group = ([^\n]*)", TEAM_NOW_TS)
    assert groups
    named = re.findall(r"'(\w+)'", groups.group(1))
    assert list(page["groups"]) == list(page["counts"]) == named
    stage = re.search(r"type Stage = ([^\n]*)", TEAM_NOW_TS)
    assert stage
    assert [s["stage"] for s in page["stages"]] == re.findall(r"'(\w+)'", stage.group(1))


def generated_keys(name: str) -> list[str]:
    """The keys of a generated type, comments left out."""
    source = (GENERATED / f"{name}.ts").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL).split("= {", 1)[1]
    return [str(name) for name in re.findall(r"(\w+)\??:", body)]


def test_what_an_agent_does_has_the_keys_of_the_generated_type_and_leaves_out_an_unset_usage() -> (
    None
):
    full = Doing(
        state="working", repository="api", id="CF-1", usage=Usage(tokens=None, seconds=3)
    ).model_dump(mode="json")
    bare = Doing(state="over limit", repository="api", id="CF-1").model_dump(mode="json")
    assert list(full) == ["state", "repository", "id", "usage"]
    assert full["usage"] == {"tokens": None, "seconds": 3}
    assert list(bare) == ["state", "repository", "id"]
    assert generated_keys("Doing")[:4] == ["state", "repository", "id", "usage"]
    assert generated_keys("Usage") == ["tokens", "seconds"]


def test_a_last_run_leaves_out_what_is_unset_and_has_the_generated_keys_when_set() -> None:
    bare = Last(
        run="r1", repository="api", id="CF-1", stage="build", at=1.0, outcome="finished"
    ).model_dump(mode="json")
    full = Last(
        run="r1",
        repository="api",
        id="CF-1",
        stage="build",
        at=1.0,
        outcome="usage limit",
        until=9.0,
        refused="why",
        context_at=4,
    ).model_dump(mode="json")
    assert list(full) == generated_keys("Last")
    assert list(bare) == ["run", "repository", "id", "stage", "at", "outcome"]


def test_the_golden_file_is_inside_the_repository_folder_the_tests_read() -> None:
    assert Path(GOLDEN).is_file()

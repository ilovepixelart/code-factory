"""The recorded board session replayed against the service, answer by answer.

`tests/support/golden/formats/writes` holds a session the previous implementation answered: the
steps (`state.json`) and what each one answered (`steps.golden.json`: status, notice, whether an
undo was offered, error). Ticket numbers come from one database sequence here, so each golden id is
mapped to the real one and back in the sentences. Comments and answers belong to another module and
are skipped. The app sends a column limit as a number, which the recording's text bodies stood for.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    GoneError,
    NotFoundError,
)
from code_factory.stages.service import StageService
from code_factory.ticket_writes.service import TicketWriteService
from code_factory.tickets.models import TicketAddress, TicketFields
from code_factory.tickets.service import TicketService
from code_factory.undo.models import Changed
from code_factory.undo.service import UndoService
from repo_files import ROOT
from stage_fakes import FakeClock
from write_fakes import RunningOn
from write_values import file

OWNER = "owner:owner"
GOLDEN = ROOT / "tests" / "support" / "golden" / "formats" / "writes"
STATUS = {BadRequestError: 400, NotFoundError: 404, ConflictError: 409, GoneError: 410}
MISSING = {"CF-99": "CF-999999", "CF-9": "CF-999998"}


def recorded() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    steps = json.loads((GOLDEN / "state.json").read_text(encoding="utf-8"))["steps"]
    answers = json.loads((GOLDEN / "steps.golden.json").read_text(encoding="utf-8"))
    return steps, answers


@dataclass
class Replay:
    """The golden ids and the real ones of the tickets the session names."""

    real: dict[str, str] = field(default_factory=dict)
    golden: dict[str, str] = field(
        default_factory=lambda: {real: golden for golden, real in MISSING.items()}
    )
    token: str | None = None
    created: int = 4

    def bind(self, repository: str, golden_id: str, real_id: str) -> None:
        self.real[f"{repository}/{golden_id}"] = real_id
        self.golden[real_id] = golden_id

    def real_id(self, repository: str, golden_id: str) -> str:
        return self.real.get(f"{repository}/{golden_id}", MISSING.get(golden_id, golden_id))

    def address(self, key: str) -> TicketAddress:
        repository, _, golden_id = key.partition("/")
        return TicketAddress(repository=repository, id=self.real_id(repository, golden_id))

    def text(self, body: dict[str, Any], repository: str = "sample") -> dict[str, Any]:
        """The step's text values with the golden ids it names turned into real ones."""
        return {
            name: re.sub(r"CF-\d+", lambda m: self.real_id(repository, m.group()), value)
            if isinstance(value, str)
            else value
            for name, value in body.items()
        }

    def sentence(self, text: str) -> str:
        return re.sub(r"CF-\d+", lambda m: self.golden.get(m.group(), m.group()), text)


async def seed(tickets: TicketService, stages: StageService, writes: TicketWriteService) -> Replay:
    """The state the recording starts from: `sample` CF-1 to CF-4, `second` CF-1, a limit, a run."""
    replay = Replay()
    one = await file(tickets, "Specs written", labels=["docs"])
    two = await file(tickets, "Bare")
    three = await file(tickets, "Declared", parent=one.id)
    four = await file(tickets, "Archived")
    elsewhere = await file(tickets, "Elsewhere", "second", priority="medium", labels=["ops"])
    await tickets.update(two.id, TicketFields(rank=2), by="board")
    await tickets.update(three.id, TicketFields(rank=1), by="board")
    await tickets.archive(four.id, by="board")
    await stages.declare(three.id, "build", "board")
    for golden_id, ticket in (("CF-1", one), ("CF-2", two), ("CF-3", three), ("CF-4", four)):
        replay.bind("sample", golden_id, ticket.id)
    replay.bind("second", "CF-1", elsewhere.id)
    await writes.set_column_limit("spec", 2)
    writes.bind_active_runs(RunningOn(one.id))
    return replay


async def run(  # noqa: PLR0911  # one branch per step kind of the recording
    step: dict[str, Any], replay: Replay, writes: TicketWriteService, undo: UndoService
) -> Changed:
    kind, body = step["do"], step.get("body", {})
    if kind == "create":
        repository = body["repository"]
        fields = {k: v for k, v in replay.text(body).items() if k != "repository"}
        made = await writes.create(repository, fields, OWNER)
        replay.created += 1
        replay.bind(repository, f"CF-{replay.created}", made.id)
        return Changed(notice="", undo=None)
    if kind == "duplicate":
        copy = await writes.duplicate(replay.address(step["ticket"]), OWNER)
        replay.created += 1
        replay.bind(copy.repository, f"CF-{replay.created}", copy.id)
        return Changed(notice="", undo=None)
    if kind == "update":
        repository = step["ticket"].partition("/")[0]
        return await writes.update(
            replay.address(step["ticket"]), replay.text(body, repository), OWNER
        )
    if kind == "move":
        return await writes.move(
            replay.address(step["ticket"]),
            body["stage"],
            [f"{key.partition('/')[0]}/{replay.real_id(*key.split('/'))}" for key in body["order"]],
            OWNER,
        )
    if kind == "delete":
        return await writes.delete(replay.address(step["ticket"]))
    if kind == "bulk":
        keys = [f"{k.partition('/')[0]}/{replay.real_id(*k.split('/'))}" for k in body["tickets"]]
        return await writes.bulk_request({**body, "tickets": keys}, OWNER)
    if kind == "limit":
        raw = body["limit"]
        value: object = None if raw == "" else int(raw) if raw.isdigit() else raw
        return await writes.set_column_limit(step["stage"], value)
    assert kind == "undo", kind
    assert replay.token is not None
    return await undo.undo(replay.token, OWNER)


async def test_every_recorded_answer_is_given_again(
    writes: TicketWriteService,
    tickets: TicketService,
    stages: StageService,
    undo: UndoService,
    clock: FakeClock,
) -> None:
    steps, answers = recorded()
    replay = await seed(tickets, stages, writes)
    seen: list[tuple[int, int, str, str, bool]] = []
    expected: list[tuple[int, int, str, str, bool]] = []
    index = 0
    for step in steps:
        if step["do"] == "wait":
            clock.advance(step["seconds"])
            continue
        golden = answers[index]
        index += 1
        if step["do"] in {"comment", "answer"}:
            continue
        status, notice, error, offered = 200, "", "", False
        try:
            answer = await run(step, replay, writes, undo)
            notice, offered = answer.notice, answer.undo is not None
            replay.token = answer.undo or replay.token
        except CodeFactoryError as refused:
            status = next(code for kind, code in STATUS.items() if isinstance(refused, kind))
            error = replay.sentence(str(refused))
        seen.append((index - 1, status, replay.sentence(notice), error, offered))
        expected.append(
            (
                index - 1,
                golden["status"],
                golden.get("notice", ""),
                golden.get("error", ""),
                bool(golden.get("undo", False)),
            )
        )
    assert seen == expected
    assert len(seen) == 70 - 9  # nine comment and answer steps belong to the talk module


def test_the_recording_has_the_steps_this_replay_counts() -> None:
    steps, answers = recorded()
    assert (len([s for s in steps if s["do"] != "wait"]), len(answers)) == (70, 70)
    assert sum(1 for s in steps if s["do"] in {"comment", "answer"}) == 9


def test_a_golden_ticket_the_board_never_had_maps_to_a_real_one_that_is_not_there() -> None:
    replay = Replay()
    assert replay.real_id("sample", "CF-99") == "CF-999999"
    assert replay.sentence("no ticket CF-999999") == "no ticket CF-99"

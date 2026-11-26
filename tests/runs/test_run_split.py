"""Starting a split: a run of stage split, asked to file the brief's pieces as child tickets."""

from dataclasses import dataclass, field

import httpx
from fastapi import FastAPI

from code_factory.runs.models import StartOptions
from code_factory.runs.rules.split import split_prompt
from code_factory.runs.service import RunService
from code_factory.tickets.models import NewTicket
from code_factory.tickets.service import TicketService


@dataclass
class Starts:
    """Stands in for the run service: records each start."""

    seen: list[tuple[str, str | None, StartOptions | None]] = field(default_factory=list)

    async def start(
        self, ticket_id: str, *, stage: str | None = None, options: StartOptions | None = None,
        by: str,
    ) -> None:  # fmt: skip
        del by
        self.seen.append((ticket_id, stage, options))


async def _ticket(app: FastAPI) -> str:
    made = await app.state.services.get(TicketService).create(
        NewTicket(repository="sample", title="Checkout", description="Pay for an order."), by="o"
    )
    return str(made.id)


async def test_a_split_starts_a_split_run_asked_to_file_the_briefs_pieces(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    starts = Starts()
    app.state.services.add(RunService, starts)
    ticket = await _ticket(app)

    answer = await client.post(
        f"/api/tickets/sample/{ticket}/split", json={"brief": "Cards, then wallets."}
    )

    assert answer.status_code == 201
    assert answer.json()["notice"].startswith(f"Started a split of {ticket}")
    [(started, stage, options)] = starts.seen
    assert (started, stage) == (ticket, "split")
    assert options is not None
    assert options.prompt == split_prompt(
        ticket, "Checkout", "Pay for an order.", "Cards, then wallets."
    )


async def test_a_split_without_a_brief_starts_nothing(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    starts = Starts()
    app.state.services.add(RunService, starts)
    ticket = await _ticket(app)

    blank = await client.post(f"/api/tickets/sample/{ticket}/split", json={"brief": "  "})
    odd = await client.post(f"/api/tickets/sample/{ticket}/split", json={"brief": "x", "n": 2})

    assert (blank.status_code, blank.json()["detail"]) == (400, "a split needs a brief")
    assert [e["pointer"] for e in odd.json()["errors"]] == ["/body/n"]
    assert starts.seen == []


def test_the_prompt_names_the_parent_the_brief_and_the_tool_to_file_with() -> None:
    prompt = split_prompt("CF-3", "Checkout", "", "  Cards.  ")
    assert "create_ticket" in prompt
    assert prompt.endswith("The parent ticket is CF-3: Checkout\n\nThe brief:\n\nCards.\n")

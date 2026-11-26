# Ticket writes

`src/code_factory/ticket_writes` holds every change the app makes to a ticket card (create, edit,
move and drag, bulk, archive, delete, duplicate, links, rank) and the work-in-progress limit of a
column. `TicketWriteService` (`service/`) is the one write path for the app, the MCP tools and the
modules that file tickets; it holds each change to the board's rules in the sentences the app
shows (`rules/`, pure) and writes it, with its activity, in one transaction through
`TicketService.unit`. The rules are tested against the recorded session in
`tests/support/golden/formats/writes` (`tests/integration/ticket_writes/test_write_golden_replay.py`).

## How a change is made

A rule returns a plan or a refusal sentence; the service raises `BadRequestError(sentence)` or
applies the plan inside `TicketService.unit([repository], wait=write_wait)`. The unit holds the
repository's lock, so two writes to one repository take turns and a lock not got in `write_wait`
seconds (20) is `UnavailableError("the board is busy; try again")` with nothing written.

| Change | Answer | Undo offered when |
|---|---|---|
| `create` | `TicketAddress` | never |
| `update` | `UpdateResult(notice, undo, changed)` | `archived` flipped |
| `move` | `Changed` | the move pinned the card to a column it was not pinned to (an empty column clears the pin and offers none) |
| `bulk`, `bulk_request` | `Changed` | always (an empty one when nothing changed) |
| `delete` | `Changed` | always |
| `add_link`, `remove_link` | `Changed` | always |
| `duplicate`, `set_rank`, `set_column_limit` | none | never |

## Undo

`UndoService` (module `undo`) stores the inverse and claims it once within 30 seconds; this module
registers the kind `tickets.revert`, whose payload is `{"ops": [...]}`: `fields` (put values back
while the fields still hold what the change left), `stage` (the column pin), `rank`, `restore`.
Every `expect` is checked before anything is written and a mismatch is `ConflictError` naming the
field. The column pins go back first, each by a compare-and-set that fails when the column changed
since the check (`StageService.declare(expect=...)`; a pin cannot be written while the unit holds
its ticket), then the field, rank and restore ops in one unit; a refusal of the unit puts the pins
already written back. A rank never blocks an undo. The token is
consumed even when the handler refuses.

## Gotchas

| Gotcha | Behaviour |
|---|---|
| Python's `float` and `int` read `1_0` and other scripts' digits | `budget_text` and `parallel_text` read ASCII decimal only, and store the budget as a plain decimal (`1e3` is `1000`) because the tickets module takes `[0-9]+(\.[0-9]+)?`; a budget whose plain form would pass 30 digits either side of the point is refused, so `1e-999999999999` is never written out |
| Column changes | `update(stage=...)` declares exactly that column (`StageService.declare`, no evidence asked, after the refusals `assess` holds); `move` and `bulk` use `StageService.move` and `move_many` (the keep-following-evidence rule) |
| Records of an edit | `field {name, value}` per changed name in the order given (a description records an empty value), then `archived` or `restored`; the column record is the stages module's and follows them |
| Blank title on create | the tickets module refuses it (`a ticket needs a title`) |
| Branch | `branch` is checked against `GitService.facts` only when it differs from the held one and git is readable; a malformed name is refused by `GitService.branch_refusal` first |
| Column limits | whole numbers from 1 to 2147483647 (`null` clears); the table refuses a name that is not a board column |
| Links | a link is the holder's whole list with one entry added or removed, worked out under the repository lock, so two links added at once both stay; an old link to a deleted ticket never stops the list from changing (the tickets module checks only the targets a write adds) |
| Bulk undo | holds an op only for a card the bulk changed, so a card left as it was never blocks the undo |
| Drop order | `move` numbers each repository's cards by position in the drop; unknown repositories, ids and malformed entries are skipped silently |

Other modules bind two questions in their `provide`: `bind_active_runs` (delete is refused while an
agent runs on the ticket) and `bind_duplicate_question` (the question appended to a new ticket's
description). Unbound means no run and no question.

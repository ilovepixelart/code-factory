# The board

`src/code_factory/board` answers every read the web app makes about the work as a whole: the board,
the filtered ticket list, one ticket's page, the archive, the repositories and the saved views. It
owns no ticket data: it assembles other modules' services and decides the words a card says.
Routes are `board/routes.py`; the service is `board/service/`; the pure rules are `board/rules/`
(tests in `tests/board/`).

## Reads

| Method | Reads |
|---|---|
| `board()` | tickets, stage assessments, open questions, sessions, runs, checks, pull requests, claims |
| `tickets(filters)` | the same cards, filtered by `TicketsFilter` |
| `ticket_page(repository, id)` | one card plus documents, talk and history, review verdict |
| `archive(query)` | tickets and stage assessments, release names |
| `month_budget`, `evidence_summary` | what the page shows, for other modules (the delivery module reads the summary) |

A read writes nothing (`tests/integration/board/test_board_page_service.py` spies on the statements) and keeps
no cache: the number of statements is the same at 10 and at 40 tickets. The services answer in
separate units of work, so one answer may combine states a few milliseconds apart; the next poll
(3 s) corrects it. `board()` is an ETag over the compact body (`rules/etag.py`); the 304 is the
route's.

## Ports

What the runs, checks and delivery modules will supply is read through the Protocols in
`board/ports.py` (`CardRuns`, `CardChecks`, `CardDelivery`, `CardQueue`, `ColumnLimits`). Until a
module registers a provider, `board/adapters.py` answers as a board with no runs, no check and no
pull request record does. Claims come from the team module. `module.board_sources` is the one place
that picks a provider: replace the null one there when its module lands.

## Rules worth knowing

- A card is built from `CardFacts` by `rules/card.py`; a key a card has nothing to say for
  (`spent_estimated`, `delivery_event`, `checks_configured`, `queue`, `overlap`, `holder`) is absent,
  never null. `spent` is the integer 0 when no run exists.
- Column order is rank (0 last), then the natural order of the id (`rules/order.py`).
- A card's stage is the stages module's assessment; a ticket the assessment names `released` has no
  card and appears in the archive.
- `stage_since` is the newest `stage` record into the ticket's column, else its creation; an archived
  ticket's `archived_at` is the release publish time, else its last `archived` record, else its last
  record (`ActivityService.latest_marks`, `rules/marks.py`). An edit changes neither.
- A read awaits its sources one after another, a fixed number of reads however many tickets there
  are. The tests give every service units of work on one shared connection, where concurrent reads
  interleave their savepoints and fail, so the reads are not fanned out in a task group.

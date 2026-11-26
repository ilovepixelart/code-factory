# The ticket and memory store

Everything the board knows about tickets and memory lives in Postgres and is reached through the
services of two modules: `tickets` and `memory` (`src/code_factory/<module>/service`). The HTTP
routes and the MCP tools call these services and nothing below them. The columns and constraints
are in each module's `tables.py`; this page says why they are shaped so.

## Rules every table keeps

- Every column is `NOT NULL` (`test_columns_use_the_postgres_types_the_rules_ask_for`). An
  optional text field is `''` when unset, which is also how the app reads it. An optional
  relation is a row of its own that exists only while the fact holds.
- Allowed values are named check constraints. Ticket types, priorities, pull request states and
  memory kinds take their lists from the DTOs in `models`, and link kinds from
  `tickets/tables.py`, so the database refuses what the service would.
- A list that is filtered or read whole (labels, `supersedes`, `cites`) is a `text[]` column.

## Tables

| Table | Key | Why it is shaped so |
|---|---|---|
| `tickets` | `number`, an identity `GENERATED ALWAYS` | `trashed` hides a deleted ticket from every read (the row and its history stay); `TicketService.unit(repositories, wait=)` is the one transaction other modules write tickets through (fields, branch, archived flag, ranks, records, trash; `ticket_writes` is its caller, see `docs/ticket-writes.md`), an advisory lock per repository in name order, `UnavailableError` when one is not got in `wait` seconds. There is no declared stage in it: the column is read from the facts. `scratch` marks a ticket filed for one eval run (`TicketService.create_scratch`): it is in no list, count, flow or source read, and `delete_scratch` removes it with its history. The number is the identity (`CF-<number>`, `rules.ticket_id`); it comes only from the sequence, so an insert that names one is refused. The facts the column is read from (`branch`, `merged`) are plain columns; the column itself is not stored. |
| `ticket_links` | `(ticket_number, kind, linked_number)` | Parent, `blocked_by` and `caused_by` as rows with foreign keys, so a link always names an existing ticket. `position` keeps the order blockers were written in. A partial unique index allows one parent per ticket; a check refuses a link to itself. The holder's links go with it (`CASCADE`); a linked ticket cannot be deleted (`RESTRICT`). |
| `ticket_pull_requests` | `ticket_number` | One row while a ticket has a pull request: its number, state (`open`, `closed`, `merged`) and address. |
| `ticket_documents` | `(ticket_number, name)` | A document is markdown in a row, not a file. `version` starts at 1 and rises on every write, so a writer names the version it read and a stale write is refused. |
| `ticket_mock_files` | `(ticket_number, name)` | A mock image is bytes in a row (`bytea`), served by the page: png, jpeg, gif or webp by file name, never SVG, 1 byte to 16 MiB (`rules.check_mock`, and a check constraint). The ticket's rows go with it (`CASCADE`). |
| `ticket_activity` | `id`, an identity | Append-only: a trigger refuses `UPDATE`, `DELETE` and `TRUNCATE` (a `DELETE` passes only for a scratch ticket), and a ticket with history cannot be deleted (`RESTRICT`). `by` is the actor, indexed with `kind` for counts. `data` is `jsonb`. |
| `memory_entries` | `id`; `(repository, name)` unique | `name` is the id the app shows (`<day>-<first eight words>`, `-2` when taken, `rules.entry_name`). A retired entry keeps its row with the reason in `retired`, which is the history the Memory page lists. `proposed_by` keeps who proposed an entry after it is approved. |
| `memory_deliveries` | `(run_id, repository, entry_id)` | Which entries a run was given when its rules were delivered, and `left_out` for those the budget cut. `run_id` has no foreign key: the runs table belongs to a later module, which adds its own with `ON DELETE CASCADE`. The entry's foreign key cascades, which fires only on a purge (entries are retired, never deleted). Written once per run and entry (`ON CONFLICT DO NOTHING`), never pruned. |
| `repositories` | `id`; `name` unique | A repository is addressed by its folder name, so the unique name is what refuses a second folder of the same name (`RepositoryService.track`). It holds no foreign key from other modules: untracking must not delete what shipped. `path` is the main checkout the caller resolved. |

A source (an issue address, an error fingerprint) is filed once per repository: the partial unique
index `uq_tickets_repository_source` on `tickets (repository, source)` where `source <> ''` refuses
a second ticket, and the repository turns that into a `ConflictError` naming the source.

## Findings

A review writes `finding` records (`F<n>`, counted per ticket), `finding.kept` for one it
continues, and `review_submitted` with the document version. A finding's state is read from its
records (`rules.findings_of`), never stored: `open` when raised or kept (a kept one reopens a
closed finding), `dismissed` after `finding.dismissed` (a Build run, with its reason) or
`finding.closed` with state `dismissed`, `fixed` after `finding.closed` with state `fixed` (the
owner, or a later review that no longer raises it). The finding records and `review_submitted` are
written by `ReviewService` only: `check_kind` refuses them in a hand-appended record, and `coordinator_edit` too: the undo
writes the value that record holds, so only `update(coordinator=True)` writes it.

## The coordinator

`TicketService.update(..., coordinator=True)` accepts only `priority`, `labels`, `blocked_by` and
`rank` and records each change as `coordinator_edit` (`name`, `from`, `to`, each as the field holds it).
`CoordinatorService.edit` offers an undo token through the undo store for the fields it changed (the token holds the `from` and `to` of those edits, so a later edit is never undone by an earlier token);
`undo_edit` puts one field back by name as the actor's own edit and is refused once the field no
longer holds what the coordinator left.

### Why `ticket_activity.data` is jsonb

Each record kind carries keys of its own. A stage move has `from` and `to`, a check run has its
exit code and step times, and a judged attempt has a list of objects. The previous
implementation's log had dozens of kinds and gained new ones often. As columns, each record would
leave almost all of them empty, and every new kind would need a migration. The fields that are
queried (`ticket_number`, `kind`, `by`, `at`) are columns. Postgres `jsonb` does not keep the
order of an object's keys, so `data` reads back in `jsonb`'s own order, not the order it was
written in.

## The column rule

The column is computed, never stored, by `tickets/rules` `column_of(branch, pull request state,
merged)`:

| Facts | Column |
|---|---|
| merged (by hand, or the pull request is `merged`) | Merged |
| an open pull request | Review |
| a branch | Build |
| none of these | Spec |

Archiving is a separate fact: `TicketFilter.archived` (default `False`) keeps an archived ticket
off the board whatever its column. The facts change only through `TicketService` (`set_branch`,
`clear_branch`, `set_pull_request`, `clear_pull_request`, `set_merged`, `archive`,
`unarchive`). When the column moves, it records a `stage` activity with `from` and `to`; a change
that leaves the ticket as it was records nothing. The board order within a column is rank first,
unranked (`0`) after every ranked ticket, then the number (`TicketRepository.select`).

## Units of work

Each service method opens the unit of work it was built with (`docs/architecture.md`), and each
write runs in one transaction. A write that reads what it changes first locks the row it reads
(`SELECT ... FOR UPDATE`): the ticket for an edit, a fact, a document or a review, and the entry
for a memory decision. That makes a document's version check, the parent cycle check, finding
numbers and the column move safe against a concurrent writer. Appending activity needs no lock.

## Memory writes other modules build on

`MemoryService.add_admission(check)` registers a check that `add` and `propose` run after their own
checks and before the insert, told who writes the entry and how (`Intake`), so a module that
depends on memory adds rules without memory importing it. Admissions run under a lock on the
repository's additions, so a check that reads the store sees every earlier write;
`add_preparation(prepare)` registers one whose slow part (files, git) runs first, before the
transaction opens, and returns the check that runs under the lock. `apply(patches, by)` writes explicit
entries in one unit of work with no admission and answers one before-image per patch;
`restore(images)` puts them back and refuses (`ConflictError`) a row that changed after its image.

## Memory beyond storing it

`memory_extras` (`src/code_factory/memory_extras/`) owns everything about an entry that is not stored
state: where it loads (`rules/scope.py`), whether it still holds (stale, due, overdue, ended,
superseded, enforced by a test, unused), what a run is given within the 8,000 character budget
(`rules/budget.py`, `MemoryExtrasService.rules_for`, `deliver`), the checks an entry meets on its way
in (`MemoryExtrasService.prepare_admission`, registered on `MemoryService` by `module.py`), the Memory page and
the owner's writes. A write goes through `MemoryService.apply` and answers the images that
`MemoryExtrasService.restore` takes back; the add goes through `MemoryService.add_with_images`.
Nothing imports it except `app.py` and, through `service` and `models`, routes, tools and commands.

Gotchas the code cannot say:

- Test names (what makes a lesson's guard `enforced`) come from `DefinedTests`: one listing per
  repository, cached by the commit its main checkout holds, read only when an entry has a guard or
  a cite. A listing of 512 KiB of test files or more is parsed in a spawned process (the Python
  files are parsed with `ast`: 266 ms for 2.2 MB measured), a smaller one in a worker thread.
- An admission check runs inside the transaction `MemoryService.add` holds on the repository's
  additions, so it reads CLAUDE.md and, only with `check_pairs`, the test names through the
  adapters (each under a timeout, a failure reads as empty). The Memory page's add does not check
  pairs; the `remember` command and the MCP propose do.
- Knowledge search ranks BM25 over whole words of the candidates (memory entries, ticket documents,
  tracked README.md, CLAUDE.md and `docs/*.md`); a word's idf counts the candidates, floored at
  `1e-6` as SQLite's FTS5 floors it. A snippet is the 12-word window holding most query words.
- The page lists an entry that ended (`expires` passed, or its `until` ticket merged) under History
  with `expired <day>` or `ended when <id> merged`, and leaves it out of pairs and consolidations.

## Tests

`tests/tickets`, `tests/memory` and `tests/memory_extras` test the rules with plain inputs and the services against the
test database, inside the rolled-back transaction `tests/conftest.py` sets up. Sequences are not
transactional: a rolled-back test still moves numbering on, so number expectations are relative
to a number the test was issued.

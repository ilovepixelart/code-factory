# Releases

`src/code_factory/releases` holds a repository's release notes and which release named a ticket.
Columns and constraints are in `tables.py`; the use cases are `ReleaseService` in `service.py`.

## States

A release is derived from its columns, never stored (`rules.state_of`):

| State | Columns | What it means |
|---|---|---|
| draft | `published_at` empty | notes editable; names no ticket |
| published | `published_at` set | notes final; `release_tickets` lists the ids the notes name |
| tagged | `tagged_at` set | the tag reached origin |

`repository` and `ticket_id` have no foreign keys: untracking a repository keeps what shipped, and
a purged ticket cannot block a release. A version is three decimal numbers of up to nine digits
(`rules.is_version`, so every version sorts and fits an index entry); the service checks the
length and `ck_releases_version` the form. A ticket id in notes has at most 18 digits.

## Behaviour the code does not say

- `draft` lists the repository's merged tickets that no published release names, archived ones
  included, then inserts with `ON CONFLICT DO NOTHING`: a taken version is a `ConflictError`
  without a read that could race another process.
- `publish` locks the row, derives the ids from the notes (`rules.ticket_ids_in`: `CF-1` in
  `see CF-1.`, not in `CF-12`, `XCF-1` or `a-CF-1`) and writes them in the same transaction.
- `get` and `list` read releases and their ticket ids in one statement, so a state and its ids
  always agree.
- `naming` answers for published releases only, in one statement whatever the number of refs.
  A ticket two releases name belongs to the one with the earliest `published_at`.
- The tag use case (git, the gate pass) lives in the commands module. It calls
  `record_tag_commit` before pushing, so a crash between the push and `record_tagged` resumes, and
  a commit once recorded is never replaced.
- `code-factory release draft|show|edit|publish VERSION` and `code-factory release list` take
  `[--repository PATH]`: any folder inside a tracked repository (the current directory by
  default), resolved to the innermost tracked checkout that contains it, so a subfolder or a
  worktree names its checkout. A folder inside no tracked repository is refused (`NotFoundError`),
  never turned into a new repository's release.

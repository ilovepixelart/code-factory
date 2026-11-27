# Settings

The `settings` module reads and checks what a tracked repository keeps in `.code-factory/`:
`config.toml`, `exceptions.toml`, `templates/*.md` and `agents/<stage>.md`. Its one table,
`intake_key_grants`, records which repository and address a tracker key may serve; a second,
`board_settings`, holds the two board-wide whole numbers, `agent_slots` (the cap on agent runs over
all repositories) and `prune_days` (the days a prune keeps). Every other
module asks `SettingsService` (`src/code_factory/settings/service/__init__.py`); none parses TOML itself.

The keys and what each takes are in [reference/config.md](reference/config.md), generated from the
models in `settings/models/config.py`. The commands are in [reference/commands.md](reference/commands.md).
The module map, the [feature map](reference/feature-map.md) and the
[database tables](reference/database-tables.md) come from `app.MODULES` and the tables on
`platform.db.Base`. Every page is rewritten by `code-factory docs --out docs/reference` and a test
fails when a committed copy differs from what the code produces. A module that adds a command, a
route or a table changes these pages: regenerate them after merging.

## Two readings of one file

| | `load` | `check_config` |
|---|---|---|
| Invalid key | dropped, the rest read | reported as `path:line: message` |
| Unknown table or key | ignored | reported |
| Automation or scorer entry with any key off | skipped whole | reported |
| Unreadable, non-table or syntactically broken file | an empty config | reported |
| Raises | never | never |

Both come from the same findings (`settings/rules/config.py`), so they cannot disagree about what
is wrong. A key reads `None` when unset: the default of a key belongs to the module that acts on it.
Only `tickets.prefix` (`CF`) is defaulted here.

## Rules worth knowing

- The configuration is read from a repository's main checkout only. A branch that edits
  `config.toml` takes effect when it merges: `config show` reads the main checkout of the
  repository holding PATH, while `config check` validates the tree it is run in.
- `load` reads up to 256 KiB once per call and caches the parse by exact contents for 64 roots.
  Same-size rewrites take effect even if the file timestamp stays the same. The returned object is
  shared.
- A checks container mount is held away from the secret folders under `~/` read as a synthetic
  `/home` and as the real home folder, so an absolute spelling of either is refused too. Mounts
  compare by the folder they reach: `//` is folded and links are followed only below the real
  home folder and the repository (never into the synthetic `/home` elsewhere, which can be an automount
  map: a link there is refused before it is touched, and an explicit host in `/home` outside the
  real home is refused), by `lstat` and `readlink` one component at a time (a component or
  link target on `/net`, `/Volumes`, `/mnt` or `/Network` is refused before it is touched; so is a
  host path that starts there, or holds a control character). A resolution gets 2 s and one of 4
  process-wide workers; one that fails, loops, times out or finds no worker counts as reaching a
  secret. Each path resolves once per scan, and a scan has a 6 s deadline: past it `check_config`
  reports one problem naming `config.toml` and the mounts it could not judge, and `load` raises
  `ConfigUnjudgedError` with the same sentence instead of returning an empty config; so does a
  `stat` or read of the file that times out (5 s), since it may hold mounts. A config with
  mounts is re-judged on every load.
- Files are read below the root with no link followed (every folder and the file open with
  `O_NOFOLLOW`), at most 256 KiB for config and exceptions and 64 KiB for a template, valid UTF-8
  or the file reads as missing. A file that is present but cannot be read is a problem in a check,
  never a silent skip. A lockfile is read up to 2 MiB (pnpm) or 8 MiB (Cargo).
- `check_exceptions` needs facts from the tickets module (does a ticket exist, which tickets share a
  branch). That module calls `SettingsService.bind_ticket_facts` from its `provide`; until it does,
  the report says `ticket references` are unchecked instead of passing them.
- An expired exception fails on main's own tree and on a branch whose tree (committed or not)
  differs from the fork point in an exception, an ignore or a locked version; on any other branch
  it is a note. The fork point is `origin/HEAD`,
  then `main`, then `master`.
- `review_guide(root)` is `.code-factory/REVIEW.md` as the base branch commits it (the first of
  `origin/HEAD`, `main`, `master` that holds a commit, as branches, never tags), stripped, with the ref it came from; a guide
  edited on a ticket's branch or not committed is not read, and an empty one is None.
- `board_settings()` reads and `set_board_setting(key, value)` writes the board-wide numbers; None
  clears a key, 0 is a value, and an unset key reads None. Column limits belong to the tickets module.
- A tracker key may go only to its tracker's own host or this machine (`tracker_allowed`), is named
  only under `CODE_FACTORY_INTAKE_`, and serves only the repository and address its grant names.
  The check compares the repository as text, as the caller passes it.
- `[intake]` takes tickets from Linear, Jira and Slack besides GitHub issues
  (`delivery/adapters/trackers.py`), each read only with a key this machine granted to that
  repository at that address (`code-factory secret set <name> --repository --url`),
  the key the `*_token_env` field names, from the credential store, else the environment. Linear: open issues (state type not completed, canceled or
  duplicate) with `linear_label`, and only the key's own with `linear_assigned`. Jira: the issues
  of `jira_jql` whose status category is not done, page after page up to 1,000 a poll; Jira
  refuses a JQL with no search restriction.
  Slack: the messages of `slack_channel` carrying `slack_reaction`, each linked by its permalink.
  A Bug type or label files a bug, anything else a feature; Linear's priority 1 to 4 and Jira's
  Highest to Lowest (or Blocker to Trivial) become urgent to low, a due date carries over, a Jira description is
  converted to markdown. Parent and blocking links are not carried.

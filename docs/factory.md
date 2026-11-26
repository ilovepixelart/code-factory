# The factory module

`code_factory.factory` answers "what did a cohort of work cost and how did it go": runs, pull
requests, cycle time, cost per pull request, scorer cards, self-improvement pull requests. It
stores nothing (no table, no migration, no setting): every answer is computed on each read from
five ports in `factory/ports.py`, so a figure cannot drift from the module that owns its fact.
Routes are in `factory/routes.py` (`/api/factory/*`); the figures are pure functions in
`factory/rules/`, each pinned by the hand-worked fixture in `tests/support/factory_values.py`.

## Providers

The factory reads runs and costs from Runs, pull requests from Delivery, and scorer answers from
Evals. The self-improvement provider reports unavailable because there is no source of
self-improvement pull requests. The composition root wires these providers to the factory's ports.
A provider failure returns HTTP 503 with the reason.

## Definitions that decide the numbers

- A range is half open `[from, to)` in UTC; default the 30 days up to now, at most 366 days.
- The cohort is the pull requests first observed in the range. A merge after `to` still counts as
  merged for its cohort; a merge stamped after `now` counts as open.
- "Merged in period" counts merges inside the range whenever the pull request opened, so it can
  exceed the cohort's merged count.
- A pull request's cost is its ticket's priced runs started before it ended, divided by the
  ticket's number of pull requests. A run with no recorded cost is unpriced, not free (0.0 is
  priced). Judge, eval and benchmark runs are measurement spend, never in a pull request's cost.
- A negative duration is dropped, never clamped to zero.
- Medians, not means; stage medians do not add up to the total median.

The numbers choose which runs to investigate; they do not prove a cause.

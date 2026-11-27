# The factory module

`code_factory.factory` answers "what did a cohort of work cost and how did it go": runs, pull
requests, cycle time, cost per pull request and scorer cards. Factory stores the owner's
explicitly recorded time and rate per merged pull request. Everything else comes from the
modules that own the facts through `factory/ports.py`.
Routes are in `factory/routes.py` (`/api/factory/*`); the figures are pure functions in
`factory/rules/`, each pinned by the hand-worked fixture in `tests/support/factory_values.py`.

## Providers

The factory reads runs and costs from Runs, pull requests from Delivery, and scorer answers from
Evals. The self-improvement provider reports unavailable because there is no source of
self-improvement pull requests. The composition root wires these providers to the factory's ports.
A provider failure returns HTTP 503 with the reason.

## Definitions that decide the numbers

- A range is half open `[from, to)` in UTC; default the 30 days up to now, at most 366 days.
- The cohort is the pull requests opened in the range. Delivery keeps each URL's facts when its
  ticket changes to another pull request. A merge after `to` still counts as merged for its cohort.
  A merge stamped after `now` counts as open.
- Upgrades recover the last snapshot for each ticket and older merges with both opening and
  merge events. Older replaced pull requests without enough evidence for an outcome are absent.
- "Merged in period" counts merges inside the range whenever the pull request opened, so it can
  exceed the cohort's merged count.
- A pull request's cost is its ticket's priced runs started before it ended, divided by the
  ticket's number of recorded pull requests. A closed pull request stops accumulating cost and
  repair requests at its first observed closure. A run with no recorded cost is unpriced.
  An explicit 0.0 is priced.
- A negative duration is dropped, never clamped to zero.
- Medians, not means; stage medians do not add up to the total median.

The numbers choose which runs to investigate; they do not prove a cause.

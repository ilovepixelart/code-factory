# Deterministic tests

The gate runs on a machine shared with other agents, at load averages of 70 to 130 and beyond.
A test that passes alone and fails there has a hidden dependency on how fast the machine is. The
rules below remove the dependency; none of them is met by a retry, a skip or a longer sleep.

1. **Synchronise on an event, never on a sleep.** Wait for what the code does (an
   `asyncio.Event` it sets, a task that finishes, a row or lock the database reports) under an
   `asyncio.timeout` that only a hang reaches. A `sleep` that "gives the other task time" is a
   guess about speed. A bounded poll of a state the system itself exposes is allowed (see
   `tests/tickets/test_ticket_unit_locks.py`).
2. **The clock is injected.** A service that reads time takes a `clock`; the test passes a fixed
   one. A real clock turns a 30 s window into a race with the machine (the undo window in
   `tests/undo/test_undo_concurrency.py`).
3. **Timeouts that bound a hang are large, timeouts that are the behaviour are short.** A limit
   under test (a lock wait, an expiry) is the input of the test and stays small because the
   outcome does not depend on speed: the lock is held, so the wait always ends in a refusal. A
   limit that only guards against a hang is far above any load. A subprocess under a tight limit
   gets one derived from a measurement, with the measurement and the date in a comment.
   That work is linear is asserted as growth, not as a budget: `tests/growth.py` compares the CPU
   time of four times the input with that of the input, measured back to back, so load cancels.
4. **State shared between workers is named per test.** Under xdist each worker has a schema of
   its own and advisory locks are keyed by schema (`platform/db/locks.py`), but roles, files in
   `/tmp` and ports belong to the whole database or machine: a name made with `uuid4` keeps two
   workers, and two runs on one database, apart.
5. **No background task runs on the shared connection.** The `app` and `guarded_client` fixtures
   build the app from `IDLE_MODULES` (`tests/conftest.py`): the modules without their
   `background`. A task with an interval (the team keeper, 5 s) opens savepoints on the one
   connection the fixture's sessions share, and a test that outlasts the interval under load has
   them interleave. A test of a task builds it itself, as `tests/team/test_team_module.py` does.
6. **Unit tests do not reach the network.** In the web app, `src/test/unstubbed-fetch.ts`
   gives every test a `fetch` that records and refuses a call, and fails the test that made one.
   A test that sends requests installs `stubFetch`. A real request to the test origin would
   fail whenever it liked, in a later test.
7. **Do not let a slow side effect be the synchronisation.** A test that passed because a
   failing request took long enough for a dynamic import to finish is a race. Wait for the
   thing itself (import the module first, await the load).
8. **Prove it under load.** Reproduce the failure with contention: several copies of the test
   run side by side (`pytest -n 3` in a loop of parallel shells) with CPU burners that end by
   their own timer. See it fail, fix it, then run it 20 times green under the same contention.
   Break the fix once and see the test fail again.

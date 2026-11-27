# Native async Python: the rules for code-factory

Taken from the Python documentation (docs.python.org/3/library: asyncio-task, asyncio-dev,
asyncio-subprocess, asyncio-sync, asyncio-queue, asyncio-eventloop, asyncio-runner, contextvars)
and the AnyIO documentation (threads, cancellation), read on 2026-11-23. Each rule names
its source page.

## Starting, stopping, owning tasks

1. One entry point: `asyncio.run()`, called once (asyncio-runner). Under uvicorn the server owns
   the loop; our own long-lived work starts and stops in the FastAPI lifespan.
2. The loop keeps only weak references to tasks: "Save a reference to the result of this
   function, to avoid a task disappearing mid-execution" (asyncio-task, `create_task`). Every
   background task is owned: by an `asyncio.TaskGroup` (preferred: it keeps a strong reference,
   awaits its children and propagates their exceptions) or by a set with
   `add_done_callback(set.discard)` whose owner also retrieves the result.
3. In a `TaskGroup`, when one child fails the remaining children are cancelled and the errors
   are raised as an `ExceptionGroup` (asyncio-task). A service loop that must survive one
   failed pass catches inside the child, logs, and continues; it does not let the exception
   reach the group.
4. `gather` does not cancel the other awaitables when one raises (asyncio-task): use
   `TaskGroup` for fan-out whose parts belong together; `gather(return_exceptions=True)` only
   where every result, failure included, is wanted.

## Cancellation and timeouts

5. `CancelledError` is a `BaseException`. Clean up in `try/finally` and let it propagate:
   "TaskGroup and timeout() might misbehave if a coroutine swallows asyncio.CancelledError"
   (asyncio-task). Never `except BaseException:` or a bare `except:` without re-raising.
6. Timeouts: `async with asyncio.timeout(seconds):` (3.11) turns the cancellation into
   `TimeoutError` outside the block; `wait_for` for a single awaitable that has no timeout
   parameter of its own (subprocess `communicate`/`wait`, queue `get`/`put`, lock `acquire`).
   Every await on something outside the process (a subprocess, the database, HTTP) sits under
   a timeout.
7. `shield` protects the inner awaitable, but the caller is still cancelled (asyncio-task): use
   it only for a short final step that must complete (recording that a run ended), and keep a
   reference to the shielded task.
8. Cleanup that awaits during cancellation runs in a shielded scope (AnyIO cancellation:
   `CancelScope(shield=True)`), with its own short timeout.

## Blocking work

9. "Blocking (CPU-bound) code should not be called directly" in a coroutine (asyncio-dev). No
   `time.sleep`, no `subprocess.run`, no synchronous file or network IO, no synchronous database
   driver inside `async def`.
10. asyncio has no asynchronous file IO: regular files are read and written in a worker thread
    (asyncio-eventloop). Use `anyio.to_thread.run_sync` (FastAPI and Starlette run on AnyIO).
    Its default limiter allows 40 worker threads, and a call is shielded from cancellation
    while the thread runs unless `abandon_on_cancel=True` (AnyIO threads): pass our own
    `CapacityLimiter` for each kind of blocking work so one kind cannot starve another.
11. `to_thread` helps only IO-bound work (the GIL): CPU-heavy work (large diffs, parsing many
    documents) goes to a process pool, or is made incremental; measure before choosing.
12. Debug mode logs callbacks slower than 100 ms (`loop.slow_callback_duration`; asyncio-dev).
    The test suite runs without it: it made the suite about a fifth slower, and on loaded machines
    only a threshold of seconds did not flake. Blocking calls are caught by the static checks (ruff
    ASYNC rules and `tests/integration/test_event_loop_blocking.py`); turn debug mode on by hand to look for one.

## Subprocesses

13. `asyncio.create_subprocess_exec` with an argument list, never a shell string. Read output
    with `communicate()`: "`wait()` can deadlock when using stdout=PIPE or stderr=PIPE"
    (asyncio-subprocess). `communicate()` buffers everything in memory: for output of unbounded
    size read the stream in bounded chunks instead, into a file or a capped buffer.
14. `communicate()` and `wait()` take no timeout: wrap them in `asyncio.timeout`. On timeout or
    cancellation: terminate, wait a short grace period, kill, and ALWAYS await `wait()` so the
    child is reaped.
15. Keep a reference to every running `Process`: one that is garbage collected while running is
    killed (asyncio-subprocess). Long-running children (agent runs, checks) are owned by a
    registry in the lifespan, each in its own process group (`start_new_session=True`), and a
    signal is sent only to a pid or group that this process started, still holds and is above 1.
16. The `limit` for stream buffers defaults to 64 KiB (asyncio-subprocess): raise it only with
    a reason, and cap what is kept.

## Synchronisation and backpressure

17. asyncio's `Lock`, `Event`, `Condition`, `Semaphore` and `Queue` are not thread-safe
    (asyncio-sync, asyncio-queue): they are used only from the loop. Code in a worker thread
    talks back through `anyio.from_thread` (or `loop.call_soon_threadsafe`), never directly.
18. Always `async with` a lock or semaphore. A `Semaphore` (or AnyIO `CapacityLimiter`) caps
    concurrency: git calls per repository, agent runs, checks, outbound GitHub calls.
19. Queues are bounded (`Queue(maxsize=n)`) so a slow consumer slows the producer instead of
    growing memory; `Queue.shutdown()` (3.13) ends consumers cleanly.
20. Never hold a lock across an await of something slow or external unless the lock exists to
    serialise exactly that thing; never hold a database transaction open across a subprocess
    or an HTTP call.

## Context, database, logging

21. Context variables are copied into new tasks and propagated into `to_thread`
    (asyncio-task, contextvars): the request id and the acting user travel that way. Declare
    them at module level.
22. The database is reached only through SQLAlchemy's asyncio API on asyncpg: one
    `AsyncSession` per use case (the service opens the unit of work), never shared between tasks; the
    engine is disposed by `platform.runtime.running`, which every entry point enters. A session is not used concurrently by
    two tasks.
23. "Network logging can block the event loop" (asyncio-dev): log handlers do no blocking IO in
    the loop (a `QueueHandler` with a listener thread).
24. Async generators are closed explicitly (`contextlib.aclosing`) (asyncio-dev): this matters
    for the event stream endpoint, whose generator must stop when the client disconnects.

## Hygiene

25. Tests turn warnings into errors (`filterwarnings = ["error"]`): a never-awaited coroutine's
    `RuntimeWarning` fails the test instead of scrolling by. A task exception that is never
    retrieved is only logged by asyncio and fails nothing, which is why every task is owned and
    its result read (rule 2). Debug mode stays off in the suite (rule 12).
26. Signals are handled by the loop in the main thread (`loop.add_signal_handler`; under
    uvicorn, its own shutdown path): shutdown cancels the lifespan's task group, which stops
    background loops, ends children as in rule 14, and closes the engine.
27. Loop policies are deprecated (removal planned for 3.16): configure a loop with
    `loop_factory`, never with a policy.

## Diagnosing a slow or stuck service

- On Python 3.14, `python -m asyncio ps PID` lists tasks and their awaiters, and
  `python -m asyncio pstree PID` shows their parent and child relationships. Use the interpreter
  and attach permissions appropriate to the process. Name long-lived tasks and capture the tree
  while the symptom is present. [Python 3.14 task introspection](https://docs.python.org/3.14/whatsnew/3.14.html#asyncio-introspection-capabilities)
- Measure durable backlog, in-flight tasks, execution slots, and database pool wait separately.
  A bounded queue can still feed an unbounded number of tasks waiting on a semaphore. When
  changing admission or batching, prove the order for waiting work and verify cancellation,
  recovery after restart, and the behavior of stale or stopped rows.
- Audit cancellation at the boundary between asyncio and AnyIO. Keep shielded cleanup short and
  bounded. A cancelled await on an abandoned worker thread can leave the underlying operation
  running. Avoid scheduling conflicting work until the worker has really stopped.
  [AnyIO cancellation](https://anyio.readthedocs.io/en/stable/cancellation.html)
  [AnyIO worker threads](https://anyio.readthedocs.io/en/stable/threads.html)

## What holds these rules in this repository

| Rule | Held by |
|---|---|
| 2, 3 (owned tasks, one failure does not end the group) | `platform/background.py`, `tests/unit/platform/test_background.py` |
| 5 (CancelledError propagates) | ruff `ASYNC`, `BLE` and `TRY` rules; no `except BaseException` in `src/` |
| 6 (timeouts on outside awaits) | `platform/db/engine.py` `ping` under `asyncio.timeout`; `tests/integration/health/test_health_routes.py` (a server that never answers) |
| 9 (no blocking call in `async def`) | ruff `ASYNC2xx`, `tests/integration/test_event_loop_blocking.py` |
| 12, 25 (no debug mode in the suite, warnings are errors) | `filterwarnings = ["error"]` in `pyproject.toml`; blocking calls by ruff `ASYNC2xx` and `tests/integration/test_event_loop_blocking.py` |
| 21 (context variables) | `platform.logging.request_id_var`, set by a pure ASGI layer (`platform/web/middleware.py`) |
| 22 (sessions) | `platform/db/unit_of_work.py` (one session per use case), `tests/integration/platform/test_unit_of_work.py`; the engine is disposed in `platform/runtime.py` |
| 23 (logging never blocks the loop) | `platform/logging.py` `setup_logging` (queue and listener thread), `tests/unit/platform/test_logging.py` |
| 26 (shutdown) | uvicorn's graceful shutdown; `tests/e2e/platform/test_serve.py` sends SIGTERM to a real server |

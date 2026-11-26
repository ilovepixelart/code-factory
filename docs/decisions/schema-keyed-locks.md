# Advisory locks are keyed by schema

Every advisory lock is keyed by the hash of `<current schema>/<name>` (`platform/db/locks.py`).

**Why.** PostgreSQL advisory locks belong to the whole database. Keyed by name alone, two boards on
separate schemas of one database waited on each other, and so did the test workers, each on its own
schema; a lock taken in a savepoint is held until the outer transaction ends.

**What follows.** With no current schema the schema part is empty rather than NULL, because a NULL
key takes no lock at all. `tests/platform/test_advisory_locks.py` shows one name blocking within a
schema and not across two.

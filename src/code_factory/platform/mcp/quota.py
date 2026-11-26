"""One use of a quota at a time per actor, so two calls cannot both take the last slot."""

import asyncio
import weakref

_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def quota_lock(subject: str) -> asyncio.Lock:
    """The lock a call holds from counting the actor's uses to making the next one.

    Held in this process: a run's calls all reach the server it is connected to. The lock goes
    when no call holds it.
    """
    lock = _LOCKS.get(subject)
    if lock is None:
        lock = _LOCKS[subject] = asyncio.Lock()
    return lock

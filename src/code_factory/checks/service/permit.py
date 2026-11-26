"""One run's place among the runs a process lets go at once."""

import asyncio
from collections.abc import Awaitable


class Permit:
    """A permit of a semaphore that its holder can give up while it waits for something else.

    A run that waits for its container's turn must not hold the permit an older run needs to
    reach that turn. `release` is a no-op when the permit is not held, so a run that ends while
    it has given the permit up never frees one it does not hold.
    """

    def __init__(self, slots: asyncio.Semaphore) -> None:
        self._slots = slots
        self._held = False

    async def acquire(self) -> None:
        """Wait for a permit and hold it."""
        await self._slots.acquire()
        self._held = True

    def release(self) -> None:
        """Give the permit back; nothing when it is not held."""
        if self._held:
            self._held = False
            self._slots.release()

    async def without[T](self, waiting: Awaitable[T]) -> T:
        """Await `waiting` while not holding the permit, then take one again."""
        self.release()
        result = await waiting  # a cancel or an error leaves the permit given up
        await self.acquire()
        return result

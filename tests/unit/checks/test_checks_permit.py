"""A permit given up while a run waits for its turn, and taken again after."""

import asyncio

from code_factory.checks.service.permit import Permit


async def test_a_permit_is_free_to_another_run_while_its_holder_waits_and_held_again_after() -> (
    None
):
    slots = asyncio.Semaphore(1)
    first, other = Permit(slots), Permit(slots)
    await first.acquire()
    taken = asyncio.Event()
    let_go = asyncio.Event()

    async def waiting() -> str:
        await let_go.wait()
        return "turn"

    async def rival() -> None:
        await other.acquire()
        taken.set()
        await let_go.wait()
        other.release()

    rival_task = asyncio.create_task(rival())
    waiter = asyncio.create_task(first.without(waiting()))
    await asyncio.wait_for(taken.wait(), timeout=2)
    let_go.set()
    assert await asyncio.wait_for(waiter, timeout=2) == "turn"
    await rival_task
    assert slots.locked()  # the first run holds its permit again
    first.release()
    assert not slots.locked()


async def test_a_run_cancelled_while_it_has_given_up_its_permit_frees_none() -> None:
    slots = asyncio.Semaphore(1)
    permit = Permit(slots)
    await permit.acquire()
    other = Permit(slots)

    waiter = asyncio.create_task(permit.without(asyncio.sleep(60)))
    await other.acquire()  # succeeds because the waiting run gave its permit up
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    permit.release()  # the run unwinds: it holds nothing, so nothing is freed
    assert slots.locked()  # the other run still holds the one permit
    other.release()
    assert not slots.locked()

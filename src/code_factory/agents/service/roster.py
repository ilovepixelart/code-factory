"""Writes and reads of the roster: add, edit, remove, move, restore a context, and undo them."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import anyio

from code_factory.agents.models.agents import AgentChange, AgentDefinition
from code_factory.agents.models.answers import AgentList, Changed, RenameGuard, UndoStep
from code_factory.agents.models.constants import ROLES, RUNTIMES
from code_factory.agents.repository import AgentRepository, ConnectionRepository, RosterLock
from code_factory.agents.rules.connections import agent_refusal
from code_factory.agents.rules.contexts import restore
from code_factory.agents.rules.gaps import gaps_of
from code_factory.agents.rules.model_checks import current
from code_factory.agents.rules.roster import apply_change, blank, move, rename_refusal
from code_factory.agents.service import undo as inverse
from code_factory.agents.service.base import Shared
from code_factory.platform.contained import SANDBOX_PROGRAM
from code_factory.platform.db import AsyncSession
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.platform.programs import find_program
from code_factory.platform.text.markdown import INLINE_LIMIT, render
from code_factory.platform.text.moments import day_minute

NO_AGENT = "no such agent"
GUARD_TIMEOUT_S = 10.0
_renders = anyio.CapacityLimiter(2)


async def _connected(session: AsyncSession, agent: AgentDefinition) -> None:
    connections = await ConnectionRepository(session).all()
    if (why := agent_refusal(agent, connections)) is not None:
        raise BadRequestError(why)


def _paused_only(change: AgentChange) -> bool:
    return change.paused is not None and change.model_fields_set == {"paused"}


class RosterService(Shared):
    """The agents of this machine, in the order the board tries them."""

    def register_rename_guard(self, guard: RenameGuard) -> None:
        """Ask `guard` before an agent is renamed."""
        self._guards.append(guard)

    @staticmethod
    async def local_harnesses(state_dir: Path) -> dict[str, bool]:
        """Check for installed executables on the board's trusted PATH without running them."""
        places = (state_dir, Path("/tmp"), Path("/var/tmp"))  # noqa: S108  # exclude temp tools
        programs = (*RUNTIMES, SANDBOX_PROGRAM)
        found = await asyncio.gather(*(find_program(name, places) for name in programs))
        return {name: binary is not None for name, binary in zip(programs, found, strict=True)}

    async def list_definitions(self) -> AgentList:
        """The roster, the runtimes with their gaps, and each agent's current check."""
        async with self._uow() as session:
            repo = AgentRepository(session)
            agents, checks = await repo.all(), await repo.checks()
        kept = {a.name: found for a in agents if (found := current(checks.get(a.name), a))}
        return AgentList(
            agents=agents,
            runtimes=RUNTIMES,
            gaps={runtime: gaps_of(runtime) for runtime in RUNTIMES},
            roles=ROLES,
            checks=kept,
        )

    async def agents(self) -> list[AgentDefinition]:
        """Every agent in roster order."""
        async with self._uow() as session:
            return await AgentRepository(session).all()

    async def get_agent(self, name: str) -> AgentDefinition:
        """The agent named `name`, else `NotFoundError`."""
        async with self._uow() as session:
            found = await AgentRepository(session).get(name)
        if found is None:
            raise NotFoundError(NO_AGENT)
        return found

    async def _locked(self, session: AsyncSession) -> AgentRepository:
        await RosterLock(session).take()
        return AgentRepository(session)

    async def add_agent(self, change: AgentChange) -> Changed:
        """Add an agent at the end of the roster."""
        async with self._uow() as session:
            repo = await self._locked(session)
            agent = apply_change(blank(), change, self._clock())
            if any(known.name == agent.name for known in await repo.all()):
                raise ConflictError(f"an agent named {agent.name} is defined")
            await _connected(session, agent)
            await repo.add(agent)
        return Changed(
            notice=f"Added {agent.name}",
            undo=inverse.step(inverse.AGENT_ADD, after=inverse.dump(agent)),
        )

    @asynccontextmanager
    async def _still(self, name: str, *, renaming: bool) -> AsyncGenerator[None]:
        """Hold every guard's writers off `name` until the rename commits, when `renaming`.

        Entered before the roster lock and left after the commit: a claim reads the roster and
        writes its lease under the guard's lock, so none lands between the answer and the write.
        Each guard is bounded by `GUARD_TIMEOUT_S` to freeze.
        """
        async with AsyncExitStack() as stack:
            for guard in self._guards if renaming else ():
                async with asyncio.timeout(GUARD_TIMEOUT_S):
                    await stack.enter_async_context(guard.frozen(name))
            yield

    async def _held(self, name: str, new: str) -> None:
        """Refuse the rename when a guard holds `name`.

        Called under the roster lock and inside `_still`: the answer cannot go stale before the
        write commits. Each answer is bounded by `GUARD_TIMEOUT_S`.
        """
        held: list[str] = []
        for guard in self._guards:
            async with asyncio.timeout(GUARD_TIMEOUT_S):
                held.extend(await guard.holds(name))
        if (why := rename_refusal(name, new, held)) is not None:
            raise ConflictError(why)

    async def edit_agent(self, name: str, change: AgentChange) -> Changed:
        """Change the agent `name`; a rename waits for what the board keeps by its name."""
        renaming = change.name is not None and change.name != name
        async with self._still(name, renaming=renaming), self._uow() as session:
            repo = await self._locked(session)
            agents = await repo.all()
            before = next((a for a in agents if a.name == name), None)
            if before is None:
                raise NotFoundError(NO_AGENT)
            after = apply_change(before, change, self._clock())
            if after.name != name and any(a.name == after.name for a in agents):
                raise ConflictError(f"an agent named {after.name} is defined")
            if after.name != name:
                await self._held(name, after.name)
            await _connected(session, after)
            await repo.replace(name, after)
        verb = "Saved"
        if _paused_only(change):
            verb = "Paused" if change.paused is True else "Resumed"
        return Changed(
            notice=f"{verb} {after.name}",
            undo=inverse.step(
                inverse.AGENT_REPLACE, before=inverse.dump(before), after=inverse.dump(after)
            ),
        )

    async def remove_agent(self, name: str) -> Changed:
        """Remove the agent `name`; its context versions and check go with it."""
        async with self._uow() as session:
            repo = await self._locked(session)
            agents = await repo.all()
            before = next((a for a in agents if a.name == name), None)
            if before is None:
                raise NotFoundError(NO_AGENT)
            await repo.remove(name)
        index = next(i for i, a in enumerate(agents) if a.name == name)
        return Changed(
            notice=f"Removed {name}",
            undo=inverse.step(inverse.AGENT_REMOVE, before=inverse.dump(before), index=index),
        )

    async def move_agent(self, name: str, column: str, direction: str) -> Changed:
        """Move the agent one place up or down among the agents of `column`."""
        if direction not in ("up", "down"):
            raise BadRequestError(f'"{direction}" is not up or down')
        if column not in ROLES:
            raise BadRequestError(f'"{column}" is not a column an agent works')
        async with self._uow() as session:
            repo = await self._locked(session)
            agents = await repo.all()
            moved = move(agents, name, column, up=direction == "up")
            before = [a.name for a in agents]
            after = [a.name for a in moved]
            await repo.reorder(after)
        return Changed(
            notice=f"Moved {name} {direction} in {column}",
            undo=inverse.step(inverse.AGENT_ORDER, before=before, after=after),
        )

    async def restore_context(self, name: str, at: int) -> Changed:
        """Make the context version of `at` (epoch seconds) current again."""
        async with self._uow() as session:
            repo = await self._locked(session)
            before = await repo.get(name)
            if before is None:
                raise NotFoundError(NO_AGENT)
            after = restore(before, at)
            await repo.replace(name, after)
        return Changed(
            notice=f"Restored {name}'s context of {day_minute(at)} UTC",
            undo=inverse.step(
                inverse.AGENT_REPLACE, before=inverse.dump(before), after=inverse.dump(after)
            ),
        )

    async def preview_context(self, text: str) -> str:
        """The HTML of a context text, raw HTML shown as text; nothing is kept."""
        if len(text) <= INLINE_LIMIT:
            return render(text)
        return await anyio.to_thread.run_sync(render, text, limiter=_renders)

    async def undo_agent(self, step: UndoStep) -> None:
        """Apply the inverse of an agent write; `ConflictError` when its target changed since."""
        handler = _HANDLERS.get(step.kind)
        if handler is None:
            raise BadRequestError(f"unknown undo kind {step.kind}")
        renamed = _undone_rename(step)
        async with (
            self._still(renamed[0] if renamed else "", renaming=renamed is not None),
            self._uow() as session,
        ):
            await RosterLock(session).take()
            if renamed is not None:
                await self._held(*renamed)
            await handler(session, step.payload)


def _undone_rename(step: UndoStep) -> tuple[str, str] | None:
    """The (name it leaves, name it restores) of an undo that renames, else none."""
    if step.kind != inverse.AGENT_REPLACE:
        return None
    before = str(step.payload["before"]["name"])
    after = str(step.payload["after"]["name"])
    return (after, before) if before != after else None


def _agent(raw: dict[str, Any] | None) -> AgentDefinition:
    assert raw is not None  # noqa: S101  # the step was built with it
    return AgentDefinition.model_validate(raw)


async def _undo_add(session: AsyncSession, payload: dict[str, Any]) -> None:
    after = _agent(payload["after"])
    repo = AgentRepository(session)
    if await repo.get(after.name) != after:
        raise inverse.changed_since(after.name)
    await repo.remove(after.name)


async def _undo_remove(session: AsyncSession, payload: dict[str, Any]) -> None:
    before = _agent(payload["before"])
    repo = AgentRepository(session)
    if await repo.get(before.name) is not None:
        raise ConflictError(f"an agent named {before.name} is defined; nothing was undone")
    await _connected(session, before)
    await repo.add(before, payload["index"])


async def _undo_replace(session: AsyncSession, payload: dict[str, Any]) -> None:
    before, after = _agent(payload["before"]), _agent(payload["after"])
    repo = AgentRepository(session)
    if await repo.get(after.name) != after:
        raise inverse.changed_since(after.name)
    if before.name != after.name and await repo.get(before.name) is not None:
        raise ConflictError(f"an agent named {before.name} is defined; nothing was undone")
    await _connected(session, before)
    await repo.replace(after.name, before)


async def _undo_order(session: AsyncSession, payload: dict[str, Any]) -> None:
    repo = AgentRepository(session)
    if [a.name for a in await repo.all()] != payload["after"]:
        raise inverse.changed_since("the order")
    await repo.reorder(payload["before"])


_HANDLERS = {
    inverse.AGENT_ADD: _undo_add,
    inverse.AGENT_REMOVE: _undo_remove,
    inverse.AGENT_REPLACE: _undo_replace,
    inverse.AGENT_ORDER: _undo_order,
}

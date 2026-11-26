"""The roster through the service against PostgreSQL: each write, its notice, its undo and the
guards that refuse it."""

import asyncio
import threading
import time

import pytest

from agents_support import Clock, Unfrozen, agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.connections import ConnectionChange
from code_factory.agents.service import AgentService
from code_factory.agents.service import roster as roster_module
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.platform.text.markdown import INLINE_LIMIT


def change(**fields: object) -> AgentChange:
    return AgentChange.model_validate(fields)


async def names(agents: AgentService) -> list[str]:
    return [a.name for a in await agents.agents()]


async def three(agents: AgentService) -> None:
    for name, roles in (("a", ["build"]), ("b", ["build", "spec"]), ("c", ["build"])):
        await agents.add_agent(change(name=name, roles=roles))


async def test_an_added_agent_is_listed_with_its_notice_and_an_undo(agents: AgentService) -> None:
    done = await agents.add_agent(change(name="writer", roles=["spec"], model="m-1"))
    assert done.notice == "Added writer"
    assert done.undo is not None
    listed = await agents.list_definitions()
    assert [a.name for a in listed.agents] == ["writer"]
    assert listed.runtimes == ("claude", "codex")
    assert listed.roles == ("spec", "build", "review")
    assert listed.wire()["problem"] == ""
    assert (await agents.get_agent("writer")).model == "m-1"


async def test_a_name_taken_is_a_conflict_with_the_boards_sentence(agents: AgentService) -> None:
    await agents.add_agent(change(name="writer"))
    with pytest.raises(ConflictError) as caught:
        await agents.add_agent(change(name="writer"))
    assert str(caught.value) == "an agent named writer is defined"


async def test_an_agent_off_the_model_is_refused_and_nothing_is_stored(
    agents: AgentService,
) -> None:
    with pytest.raises(BadRequestError):
        await agents.add_agent(change(name="writer", runtime="pi"))
    assert await names(agents) == []


async def test_an_unknown_agent_is_not_found(agents: AgentService) -> None:
    for call in (agents.get_agent("x"), agents.remove_agent("x"), agents.edit_agent("x", change())):
        with pytest.raises(NotFoundError) as caught:
            await call
        assert str(caught.value) == "no such agent"


async def test_an_edit_says_saved_and_a_pause_alone_says_paused_then_resumed(
    agents: AgentService,
) -> None:
    await agents.add_agent(change(name="writer"))
    assert (await agents.edit_agent("writer", change(model="m-2"))).notice == "Saved writer"
    assert (await agents.edit_agent("writer", change(paused=True))).notice == "Paused writer"
    assert (await agents.get_agent("writer")).paused_at is not None
    assert (await agents.edit_agent("writer", change(paused=False))).notice == "Resumed writer"
    assert (await agents.get_agent("writer")).paused_at is None


async def test_an_edit_is_undone_and_its_undo_is_refused_when_the_agent_changed_since(
    agents: AgentService,
) -> None:
    await agents.add_agent(change(name="writer", model="one"))
    first = await agents.edit_agent("writer", change(model="two"))
    second = await agents.edit_agent("writer", change(model="three"))
    assert first.undo is not None
    assert second.undo is not None
    with pytest.raises(ConflictError) as caught:
        await agents.undo(first.undo)
    assert str(caught.value) == "writer changed since; nothing was undone"
    await agents.undo(second.undo)
    assert (await agents.get_agent("writer")).model == "two"


async def test_a_rename_asks_every_guard_and_is_refused_with_what_they_hold(
    agents: AgentService,
) -> None:
    class Claims(Unfrozen):
        async def holds(self, _name: str) -> list[str]:
            return ["holds a claim on CF-3"]

    class Runs(Unfrozen):
        async def holds(self, _name: str) -> list[str]:
            return ["has 2 runs"]

    await agents.add_agent(change(name="old"))
    agents.register_rename_guard(Claims())
    agents.register_rename_guard(Runs())
    with pytest.raises(ConflictError) as caught:
        await agents.edit_agent("old", change(name="new"))
    assert str(caught.value) == (
        "old holds a claim on CF-3 and has 2 runs, so it cannot be renamed; "
        "add a new agent named new instead"
    )
    assert await names(agents) == ["old"]


async def test_a_rename_with_free_guards_is_saved_and_a_kept_name_calls_no_guard(
    agents: AgentService,
) -> None:
    calls: list[str] = []

    class Free(Unfrozen):
        async def holds(self, _name: str) -> list[str]:
            calls.append(_name)
            return []

    agents.register_rename_guard(Free())
    await agents.add_agent(change(name="old"))
    await agents.edit_agent("old", change(model="m"))
    assert calls == []
    await agents.edit_agent("old", change(name="new"))
    assert calls == ["old"]
    assert await names(agents) == ["new"]


async def test_the_undo_of_a_rename_asks_the_guards_about_the_name_it_would_leave(
    agents: AgentService,
) -> None:
    held: set[str] = set()

    class Claims(Unfrozen):
        async def holds(self, name: str) -> list[str]:
            return [f"holds a claim on CF-{name}"] if name in held else []

    agents.register_rename_guard(Claims())
    await agents.add_agent(change(name="old"))
    done = await agents.edit_agent("old", change(name="new"))
    assert done.undo is not None
    held.add("new")
    with pytest.raises(ConflictError) as caught:
        await agents.undo(done.undo)
    assert str(caught.value) == (
        "new holds a claim on CF-new, so it cannot be renamed; add a new agent named old instead"
    )
    assert await names(agents) == ["new"]
    held.clear()
    await agents.undo(done.undo)
    assert await names(agents) == ["old"]


async def test_a_rename_onto_another_agents_name_is_a_conflict(agents: AgentService) -> None:
    await three(agents)
    with pytest.raises(ConflictError) as caught:
        await agents.edit_agent("a", change(name="b"))
    assert str(caught.value) == "an agent named b is defined"


async def test_a_removed_agent_is_re_added_at_its_place_with_its_context_versions(
    agents: AgentService,
) -> None:
    await three(agents)
    await agents.edit_agent("b", change(context="one"))
    await agents.edit_agent("b", change(context="two"))
    done = await agents.remove_agent("b")
    assert done.notice == "Removed b"
    assert await names(agents) == ["a", "c"]
    assert done.undo is not None
    await agents.undo(done.undo)
    assert await names(agents) == ["a", "b", "c"]
    restored = await agents.get_agent("b")
    assert restored.context == "two"
    assert [v.context for v in restored.context_history] == ["one"]


async def test_an_added_agent_is_removed_by_its_undo_and_not_when_it_changed(
    agents: AgentService,
) -> None:
    first = await agents.add_agent(change(name="x"))
    assert first.undo is not None
    await agents.undo(first.undo)
    assert await names(agents) == []
    second = await agents.add_agent(change(name="x"))
    await agents.edit_agent("x", change(model="m"))
    assert second.undo is not None
    with pytest.raises(ConflictError):
        await agents.undo(second.undo)
    assert await names(agents) == ["x"]


async def test_a_move_changes_the_order_and_its_undo_puts_it_back(agents: AgentService) -> None:
    await three(agents)
    done = await agents.move_agent("c", "build", "up")
    assert done.notice == "Moved c up in build"
    assert await names(agents) == ["a", "c", "b"]
    assert done.undo is not None
    await agents.undo(done.undo)
    assert await names(agents) == ["a", "b", "c"]


async def test_the_undo_of_a_move_is_refused_when_the_order_changed_since(
    agents: AgentService,
) -> None:
    await three(agents)
    done = await agents.move_agent("c", "build", "up")
    await agents.move_agent("a", "build", "down")
    assert done.undo is not None
    with pytest.raises(ConflictError) as caught:
        await agents.undo(done.undo)
    assert str(caught.value) == "the order changed since; nothing was undone"
    assert await names(agents) == ["c", "a", "b"]


async def test_a_move_off_the_end_a_bad_direction_or_a_bad_column_is_refused(
    agents: AgentService,
) -> None:
    await three(agents)
    with pytest.raises(ConflictError) as end:
        await agents.move_agent("a", "build", "up")
    assert str(end.value) == "a is already first in build"
    with pytest.raises(BadRequestError) as direction:
        await agents.move_agent("a", "build", "sideways")
    assert str(direction.value) == '"sideways" is not up or down'
    with pytest.raises(BadRequestError) as column:
        await agents.move_agent("a", "deploy", "up")
    assert str(column.value) == '"deploy" is not a column an agent works'


async def test_a_context_version_is_restored_with_the_day_and_minute_in_the_notice(
    agents: AgentService, clock: Clock
) -> None:
    await agents.add_agent(change(name="w"))
    await agents.edit_agent("w", change(context="one"))
    clock.after(minutes=5)
    await agents.edit_agent("w", change(context="two"))
    done = await agents.restore_context("w", 1795435200)
    assert done.notice == "Restored w's context of 23 Nov 12:00 UTC"
    assert (await agents.get_agent("w")).context == "one"
    with pytest.raises(NotFoundError) as caught:
        await agents.restore_context("w", 5)
    assert str(caught.value) == "w has no context version of 5"


async def test_an_agent_names_a_connection_that_is_defined_and_suits_its_runtime(
    agents: AgentService,
) -> None:
    with pytest.raises(BadRequestError) as caught:
        await agents.add_agent(change(name="a", connection="gone"))
    assert str(caught.value) == "no connection named gone"
    await agents.add_connection(ConnectionChange(name="login", kind="codex-login", base_url=""))
    with pytest.raises(BadRequestError):
        await agents.add_agent(change(name="a", connection="login"))
    await agents.add_agent(change(name="a", runtime="codex", connection="login"))
    assert (await agents.get_agent("a")).connection == "login"


async def test_a_context_preview_shows_raw_html_as_text(agents: AgentService) -> None:
    html = await agents.preview_context("# Hi\n<script>x</script>")
    assert "<h1>Hi</h1>" in html
    assert "<script>" not in html


async def test_the_checks_listed_are_only_those_taken_with_the_agents_current_setup(
    agents: AgentService,
) -> None:
    assert (await agents.list_definitions()).checks == {}


async def test_long_context_previews_render_at_most_two_at_a_time(
    agents: AgentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = threading.Lock()
    running = {"now": 0, "peak": 0}

    def slow(text: str) -> str:
        with lock:
            running["now"] += 1
            running["peak"] = max(running["peak"], running["now"])
        time.sleep(0.1)
        with lock:
            running["now"] -= 1
        return text

    monkeypatch.setattr(roster_module, "render", slow)
    long = "x" * (INLINE_LIMIT + 1)
    assert await asyncio.gather(*(agents.preview_context(long) for _ in range(6))) == [long] * 6
    assert running["peak"] == 2

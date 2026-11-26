"""Connections and model checks through the service: keys that are never shown, a used
connection that cannot go, and a check that probes outside any transaction."""

import json
from pathlib import Path
from typing import override

import pytest
from stub_server import respond, serve

from agents_support import FakeStore, agents_fixture, clock_fixture, store_fixture  # noqa: F401
from code_factory.agents.adapters.files import CodexLoginFile
from code_factory.agents.adapters.probe import ModelProbe
from code_factory.agents.models.agents import AgentChange
from code_factory.agents.models.connections import ConnectionChange, Silence
from code_factory.agents.rules.model_checks import Request
from code_factory.agents.service import AgentService
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError


def agent(**fields: object) -> AgentChange:
    return AgentChange.model_validate(fields)


def conn(**fields: object) -> ConnectionChange:
    return ConnectionChange.model_validate(fields)


async def test_a_connection_lists_whether_its_key_is_set_and_never_the_key(
    agents: AgentService, store: FakeStore
) -> None:
    await agents.add_connection(
        conn(name="cloud", kind="openrouter", base_url="", key_env="OPENROUTER_API_KEY")
    )
    await agents.add_connection(conn(name="local", kind="ollama"))
    before = (await agents.list_connections()).wire()
    assert [(c["name"], c["key_set"], c["here"]) for c in before["connections"]] == [
        ("cloud", False, False),
        ("local", False, True),
    ]
    assert [k["kind"] for k in before["kinds"]][:2] == ["anthropic", "openrouter"]
    store.keys["OPENROUTER_API_KEY"] = "sk-or-secret"
    after = (await agents.list_connections()).wire()
    assert after["connections"][0]["key_set"] is True
    assert "sk-or-secret" not in json.dumps(after)


async def test_a_connection_added_twice_or_off_the_rules_is_refused(agents: AgentService) -> None:
    await agents.add_connection(conn(name="local", kind="ollama"))
    with pytest.raises(ConflictError) as taken:
        await agents.add_connection(conn(name="local", kind="ollama"))
    assert str(taken.value) == "a connection named local is defined"
    with pytest.raises(BadRequestError):
        await agents.add_connection(conn(name="x", kind="ollama", base_url="http://10.0.0.5"))


async def test_a_used_connection_cannot_be_removed_but_can_be_renamed(agents: AgentService) -> None:
    await agents.add_connection(conn(name="local", kind="ollama"))
    await agents.add_agent(agent(name="a", connection="local"))
    with pytest.raises(ConflictError) as caught:
        await agents.remove_connection("local")
    assert str(caught.value) == "agent a uses connection local"
    await agents.edit_connection("local", conn(name="renamed"))
    assert (await agents.get_agent("a")).connection == "renamed"


async def test_an_unused_connection_is_removed_and_the_removal_is_undone(
    agents: AgentService,
) -> None:
    await agents.add_connection(conn(name="one", kind="ollama"))
    await agents.add_connection(conn(name="two", kind="llama-cpp"))
    done = await agents.remove_connection("one")
    assert [c.connection.name for c in (await agents.list_connections()).connections] == ["two"]
    assert done.undo is not None
    await agents.undo(done.undo)
    assert [c.connection.name for c in (await agents.list_connections()).connections] == [
        "one",
        "two",
    ]


async def test_a_connection_edit_is_undone_unless_it_changed_since(agents: AgentService) -> None:
    await agents.add_connection(conn(name="c", kind="custom", base_url="http://localhost:1"))
    first = await agents.edit_connection("c", conn(base_url="http://localhost:2"))
    await agents.edit_connection("c", conn(base_url="http://localhost:3"))
    assert first.undo is not None
    with pytest.raises(ConflictError):
        await agents.undo(first.undo)


async def test_an_unknown_connection_is_not_found(agents: AgentService) -> None:
    with pytest.raises(NotFoundError) as caught:
        await agents.remove_connection("x")
    assert str(caught.value) == "no such connection"


async def test_a_key_is_read_set_and_forgotten_through_the_store(agents: AgentService) -> None:
    assert await agents.key_set("K_API") is False
    assert await agents.store_key("K_API") == 0
    assert await agents.key_set("K_API") is True
    key = await agents.read_key("K_API")
    assert key is not None
    assert "stored" not in repr(key)
    assert await agents.forget_key("K_API") is True
    assert await agents.read_key("K_API") is None


TOOL = json.dumps(
    {"model": "m-1", "content": [{"type": "tool_use", "name": "add", "input": {"a": 2, "b": 3}}]}
)
SUM = json.dumps({"model": "m-1", "content": [{"type": "text", "text": '{"sum": 5}'}]})


class EditingProbe(ModelProbe):
    """A probe that edits an agent's model while a check waits for its answer."""

    def __init__(self, service: AgentService, name: str, model: str) -> None:
        super().__init__()
        self._service, self._name, self._model = service, name, model

    @override
    async def ask(self, request: Request) -> tuple[int, str] | Silence:
        reply = await super().ask(request)
        await self._service.edit_agent(self._name, agent(model=self._model))
        return reply


async def agent_on(agents: AgentService, address: str) -> None:
    await agents.add_connection(conn(name="gw", kind="custom", base_url=address))
    await agents.add_agent(agent(name="q", connection="gw", model="m-1"))


async def test_a_passing_check_is_kept_listed_and_leaves_a_start_open(agents: AgentService) -> None:
    calls: list[str] = []

    def answer(head: str) -> str:
        calls.append(head)
        return respond("200 OK", TOOL if len(calls) == 1 else SUM)

    async with serve(answer) as stub:
        await agent_on(agents, stub.address)
        result = await agents.check_model("q")
    assert (result.passed, result.problem) == (True, "")
    assert (await agents.model_checks())["q"] == result
    assert (await agents.list_definitions()).checks["q"] == result
    assert [f.refusal for f in await agents.team_agents()] == [""]


async def test_a_failed_check_names_its_problem_and_refuses_a_run(agents: AgentService) -> None:
    async with serve(
        lambda _: respond("200 OK", json.dumps({"model": "m-1", "content": []}))
    ) as stub:
        await agent_on(agents, stub.address)
        result = await agents.check_model("q")
        assert (result.passed, result.problem) == (False, "answered without a tool call")
        refusal = (
            "agent q: m-1 failed its model check (answered without a tool call); "
            "test it again on the Agents page"
        )
        assert await agents.run_refusal("q") == refusal
        assert [f.refusal for f in await agents.team_agents()] == [refusal]


async def test_a_check_whose_agent_changed_meanwhile_keeps_nothing(agents: AgentService) -> None:
    def answer(_head: str) -> str:
        return respond("200 OK", TOOL)

    async with serve(answer) as stub:
        await agent_on(agents, stub.address)
        agents._probe = EditingProbe(agents, "q", "m-2")
        with pytest.raises(ConflictError) as caught:
            await agents.check_model("q")
    assert str(caught.value) == "agent q changed while its model was checked; nothing was kept"
    assert await agents.model_checks() == {}


async def test_a_check_is_kept_when_another_agent_was_edited_meanwhile(
    agents: AgentService,
) -> None:
    def answer(_head: str) -> str:
        return respond("200 OK", TOOL)

    async with serve(answer) as stub:
        await agent_on(agents, stub.address)
        await agents.add_agent(agent(name="other"))
        agents._probe = EditingProbe(agents, "other", "m-9")
        await agents.check_model("q")
    assert "q" in await agents.model_checks()


async def test_an_edit_of_the_model_makes_the_kept_check_not_current(agents: AgentService) -> None:
    async with serve(lambda _: respond("200 OK", TOOL)) as stub:
        await agent_on(agents, stub.address)
        await agents.check_model("q")
    await agents.edit_agent("q", agent(model="m-2"))
    assert await agents.model_checks() == {}


async def test_a_check_of_an_agent_without_a_local_connection_is_refused(
    agents: AgentService,
) -> None:
    await agents.add_agent(agent(name="plain", model="m"))
    with pytest.raises(BadRequestError) as caught:
        await agents.check_model("plain")
    assert (
        str(caught.value) == "agent plain has no connection on this machine to check its model on"
    )


async def test_a_start_is_refused_for_a_model_the_server_does_not_list(
    agents: AgentService,
) -> None:
    listing = json.dumps({"data": [{"id": "other", "loaded_context_length": 70000}]})
    async with serve(lambda _: respond("200 OK", listing)) as stub:
        await agent_on(agents, stub.address)
        assert await agents.run_refusal("q") == (
            "connection gw: m-1 is not among the models the server lists; set the agent's "
            "model to one the Agents page lists for the connection"
        )


async def test_codex_validates_the_model_against_the_signed_in_accounts_catalog(
    agents: AgentService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await agents.add_connection(conn(name="chatgpt", kind="codex-login"))
    await agents.add_agent(agent(name="q", runtime="codex", connection="chatgpt", model="absent"))
    login = {"tokens": {"access_token": "example-token", "account_id": "example-account"}}
    (tmp_path / "auth.json").write_text(json.dumps(login))
    agents._login = CodexLoginFile(tmp_path)
    calls: list[tuple[str, dict[str, str]]] = []

    async def version() -> str:
        return "0.123.0"

    async def catalog(address: str, headers: dict[str, str]) -> tuple[int, str]:
        if "chatgpt.com" not in address:
            return 404, ""
        calls.append((address, headers))
        return 200, json.dumps({"models": [{"slug": "present", "visibility": "list"}]})

    monkeypatch.setattr("code_factory.agents.adapters.probe.codex_version", version, raising=False)
    monkeypatch.setattr(agents._probe, "get", catalog)

    refusal = await agents.run_refusal("q")
    assert refusal == (
        "connection chatgpt: absent; choose a model available to this Codex login in Agents"
    )
    await agents.edit_agent("q", agent(model="present"))
    assert await agents.run_refusal("q") is None
    statuses = await agents.connection_status()
    assert [model.id for model in statuses.connections[0].models] == ["present"]
    assert len(calls) == 1
    assert calls[0][0] == "https://chatgpt.com/backend-api/codex/models?client_version=0.123.0"
    assert calls[0][1]["chatgpt-account-id"] == "example-account"


async def test_connection_status_reports_answers_models_and_each_agents_reach(
    agents: AgentService,
) -> None:
    listing = json.dumps({"data": [{"id": "m-1", "loaded_context_length": 70000}]})
    async with serve(lambda _: respond("200 OK", listing)) as stub:
        await agent_on(agents, stub.address)
        status = await agents.connection_status()
    wire = status.wire()
    assert wire["connections"][0]["answers"] is True
    assert wire["connections"][0]["models"][0]["id"] == "m-1"
    assert wire["reach"] == {"q": "answers"}


async def test_a_resolved_agent_carries_its_setup_and_the_default_agent_is_none(
    agents: AgentService,
) -> None:
    await agent_on(agents, "http://127.0.0.1:9")
    resolved = await agents.resolve_agent("q")
    assert resolved.setup.agent == "q"
    assert resolved.setup.model == "m-1"
    assert resolved.setup.template.startswith("claude -p")
    assert resolved.connection is not None
    default = await agents.resolve_agent(None, repository_template="t", repository_model="rm")
    assert (default.definition, default.setup.template, default.setup.model) == (None, "t", "rm")
    with pytest.raises(NotFoundError):
        await agents.resolve_agent("nobody")


async def test_a_run_connection_gives_the_environment_and_an_unset_key_refuses(
    agents: AgentService, store: FakeStore
) -> None:
    await agents.add_connection(
        conn(name="cloud", kind="openrouter", base_url="", key_env="OPENROUTER_API_KEY")
    )
    with pytest.raises(ConflictError):
        await agents.run_connection("cloud", "m")
    store.keys["OPENROUTER_API_KEY"] = "sk-x"
    run = await agents.run_connection("cloud", "m")
    token = run.env["ANTHROPIC_AUTH_TOKEN"]
    assert token is not None
    assert token.get_secret_value() == "sk-x"
    assert "sk-x" not in repr(run)


async def test_a_codex_run_on_a_keyed_connection_needs_the_broker_port(
    agents: AgentService, store: FakeStore
) -> None:
    store.keys["OPENROUTER_API_KEY"] = "sk-x"
    await agents.add_connection(
        conn(name="cloud", kind="openrouter", base_url="", key_env="OPENROUTER_API_KEY")
    )
    with pytest.raises(ConflictError):
        await agents.run_connection("cloud", "m", "codex")
    run = await agents.run_connection("cloud", "m", "codex", broker=4711)
    assert "http://127.0.0.1:4711/v1" in run.config_env
    assert "sk-x" not in run.config_env


async def test_editing_a_connections_address_drops_the_checks_taken_on_the_old_one(
    agents: AgentService,
) -> None:
    async with serve(lambda _: respond("200 OK", TOOL)) as stub:
        await agent_on(agents, stub.address)
        await agents.check_model("q")
        assert "q" in await agents.model_checks()
        await agents.edit_connection("gw", conn(base_url="http://127.0.0.1:9"))
    assert await agents.model_checks() == {}


async def test_renaming_a_connection_makes_the_kept_checks_of_its_agents_not_current(
    agents: AgentService,
) -> None:
    async with serve(lambda _: respond("200 OK", TOOL)) as stub:
        await agent_on(agents, stub.address)
        await agents.check_model("q")
        await agents.edit_connection("gw", conn(name="gateway"))
    assert await agents.model_checks() == {}  # the check names the old connection name


async def test_a_connection_edit_is_not_undone_into_a_shape_an_agent_cannot_use(
    agents: AgentService,
) -> None:
    await agents.add_connection(conn(name="c", kind="anthropic", key_env="ANTHROPIC_API_KEY"))
    done = await agents.edit_connection(
        "c", conn(kind="codex-login", base_url="https://chatgpt.com/backend-api/codex", key_env="")
    )
    await agents.add_agent(agent(name="x", runtime="codex", connection="c"))
    assert done.undo is not None
    with pytest.raises(BadRequestError) as caught:
        await agents.undo(done.undo)
    assert str(caught.value).startswith("a codex run starts only with a connection served")
    assert (await agents.list_connections()).connections[0].connection.kind == "codex-login"


async def test_a_check_in_flight_is_not_kept_when_its_connection_moved_meanwhile(
    agents: AgentService,
) -> None:
    class Moving(EditingProbe):
        @override
        async def ask(self, request: Request) -> tuple[int, str] | Silence:
            reply = await ModelProbe.ask(self, request)
            await self._service.edit_connection("gw", conn(base_url="http://127.0.0.1:9"))
            return reply

    async with serve(lambda _: respond("200 OK", TOOL)) as stub:
        await agent_on(agents, stub.address)
        agents._probe = Moving(agents, "q", "m-1")
        with pytest.raises(ConflictError) as caught:
            await agents.check_model("q")
    assert str(caught.value) == "agent q changed while its model was checked; nothing was kept"

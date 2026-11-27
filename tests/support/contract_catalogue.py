"""Every route the web app calls: method, path, the module that answers it, and the answer's shape.

The shape comes from a golden answer (`tests/support/golden/formats`) or, where none exists, from a
hand spec written from the app's own types (`web/src/generated`, `web/src/lib`). `ROUTES` is the
list the contract tests walk: the web app's calls are found in its source by
`test_contract_catalogue.py`, which fails for a call missing here; the app's OpenAPI document is
checked against this list by the same file.

A route whose module has not landed is in `PENDING`; `test_contract_catalogue.py` fails when a
pending route is already served (so the entry is removed and its shape starts being held) and
when a route is neither served nor pending.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from contract_shapes import Map, Shape, conforms, merge, shape_of, shape_of_spec
from repo_files import ROOT

GOLDEN = ROOT / "tests" / "support" / "golden" / "formats"


def _load(name: str) -> Any:  # noqa: ANN401
    return json.loads((GOLDEN / name).read_text())


def _merged(values: list[Any], maps: tuple[str, ...] = (), nullable: tuple[str, ...] = ()) -> Shape:
    """The one shape every golden value conforms to; refusing its own source would be a bug."""
    shapes = [shape_of(value, maps, nullable=nullable) for value in values]
    result = shapes[0]
    for shape in shapes[1:]:
        result = merge(result, shape)
    refused = [problem for value in values for problem in conforms(value, result)]
    if refused:
        msg = f"a shape refuses the golden it was made from: {refused[:3]}"
        raise AssertionError(msg)
    return result


# Fields the app's types allow to be null where every golden card holds an object or a value.
CARD_NULLABLE = ("hold", "check", "pull", "budget", "limited_until", "links", "due_date")
PAGE_NULLABLE = (*CARD_NULLABLE, "plan", "link", "month_budget", "default_budget", "columns")


def _board() -> Shape:
    board = _load("api/board.golden.json")
    board.pop("views")  # the web app derives its saved views; the board does not answer them
    # `limits` names only the columns that have a limit.
    return _merged([board], maps=("limits",), nullable=CARD_NULLABLE)


def _tickets() -> Shape:
    (case,) = (c for c in _load("api/answers.golden.json") if c["path"] == "/api/tickets")
    return _merged([case["body"]])


TICKETS_GOLDEN = GOLDEN / "api" / "tickets.golden.json"


def _ticket_page() -> Shape:
    # `titles`, `stages_by_id` and `linked` are keyed by ticket id: their keys are the sample's,
    # not fixed.
    views = [entry["view"] for entry in _load("api/tickets.golden.json")]
    # No golden ticket entered a column; one that did reports the seconds it spent there.
    views.append({**views[0], "columns": {"spec": 100, "build": 50, "review": None}})
    return _merged(views, maps=("titles", "stages_by_id", "linked"), nullable=PAGE_NULLABLE)


def _archive() -> Shape:
    return _merged(
        [{k: v for k, v in c.items() if k != "q"} for c in _load("api/archive.golden.json")]
    )


def _sessions() -> Shape:
    (case,) = (c for c in _load("api/answers.golden.json") if c["path"] == "/api/sessions")
    return _merged([case["body"]])


def _timeline() -> Shape:
    cases = _load("api/answers.golden.json")
    return _merged(
        [c["body"] for c in cases if c["path"].endswith("/timeline") and c["status"] == 200]
    )


def _inbox() -> Shape:
    # `Inbox` of `web/src/lib/metrics.ts`: `next_up` is null when nothing counted waits.
    return _merged([_load("metrics/inbox.golden.json")], nullable=("next_up",))


# `AgentList` of `web/src/lib/roster.ts`; the entries' own fields are the agent cards' concern.
_AGENT_LIST = {
    "agents": [Any], "runtimes": [str], "gaps": Map([{"guarantee": str, "why": str}]),
    "roles": [str], "doing": Map(Any), "last": Map(Any), "checks": Map(Any),
    "starting": bool, "problem": str,
}  # fmt: skip
# `ConnectionList` and `ConnectionStatus` of `web/src/lib/connections.ts`.
_CONNECTION_LIST = {
    "connections": [Any], "kinds": [{"kind": str, "label": str, "base_url": str, "key": str}],
    "problem": str,
}  # fmt: skip
_CONNECTION_STATUS = {"connections": [Any], "local": [Any], "reach": Map(Any)}

# `MemoryRecord` of `web/src/lib/memory.ts`; the golden has the entries' keys, not the page's.
_RECORD = {
    "id": str, "kind": str, "date": str, "source": str, "statement": str, "why": str,
    "guard": str, "repository": str, "reviewed": str, "guard_state": str, "loaded": bool,
    "left_out": bool, "superseded_by": str, "scope": str, "supersedes": str, "loads": str,
    "chars": int, "proposed": bool, "stale": bool, "incomplete": bool, "review_due": str,
    "filing": str, "received_by": [{"run": str, "ticket_id": str}], "cites?": str,
    "stale_cites?": [str], "unused?": bool, "received_count?": int, "last_received?": str,
}  # fmt: skip
_RETIRED = {
    "repository": str, "id": str, "kind": str, "date": str, "source": str, "statement": str,
    "why": str, "guard": str, "retired": str, "merged_into": str,
}  # fmt: skip


def _memory() -> Shape:
    """The Memory page: its keys from the app's types, the entries' from the golden."""
    return shape_of_spec(
        {
            "repositories": [str],
            "proposals": [Any],
            "unreviewed": [_RECORD],
            "rules": [_RECORD],
            "decisions": [_RECORD],
            "lessons": [_RECORD],
            "retired": [_RETIRED],
            "loaded_chars": int,
            "ceiling": int,
            "rules_over?": int,
            "left_out": [{"repository": str, "id": str}],
            "pairs": [Any],
            "review_queue": [_RECORD],
            "results": [{"repository": str, "path": str, "snippet": str, "open": str}],
            "matched": int,
            "page": int,
            "size": int,
        }
    )


def _usage() -> Shape:
    return _merged([_load("api/usage.golden.json")], maps=("$",))


def _flow() -> Shape:
    # `Flow` of `web/src/lib/metrics.ts`: medians, percentiles, shares and column minutes are null
    # with no data.
    nullable = ("median", "p85", "p95", "share", "spec", "build", "review")
    return _merged([case["flow"] for case in _load("metrics/flow.golden.json")], nullable=nullable)


_COUNT = {"key": str, "runs": int}
_SPREAD = {"median": float | None, "count": int}
_FACTORY_PR = {
    "url": str, "repository": str, "number": int, "ticket": str | None, "title": str,
    "state": str, "opened_at": float, "cost": float, "cost_complete": bool, "estimated": bool,
    "changed_lines": int | None, "size": str, "runs": int,
}  # fmt: skip
_FACTORY_RUNS = {
    "total": int, "by_stage": [_COUNT], "by_state": [_COUNT], "by_source": [_COUNT],
    "by_model": [_COUNT], "by_agent": [_COUNT],
}  # fmt: skip
_FACTORY_SCORERS = {
    "available": bool,
    "cards": [
        {
            "repository": str, "name": str, "question": str, "yes": int, "no": int,
            "unclear": int, "asked": int, "pass_rate": float | None,
            "average_score": float | None, "window": {"from": float, "to": float},
        }
    ],
}  # fmt: skip
_FACTORY_IMPROVEMENTS = {
    "available": bool,
    "items": [
        {
            "url": str, "number": int, "title": str, "state": str, "opened_at": float,
            "failures": int | None,
        }
    ],
}  # fmt: skip
_FACTORY_DASHBOARD = {
    "from": float, "to": float, "now": float,
    "runs": _FACTORY_RUNS,
    "prs": {"opened": int, "merged": int, "merged_in_period": int, "open": int, "closed": int},
    "series": {"bucket": str, "points": [{"start": float, "opened": int, "merged": int}]},
    "autonomy": {"share": float | None, "autonomous": int, "assisted": int, "unknown": int},
    "cycle": {
        "total": _SPREAD,
        "stages": [{"stage": str, "median": float | None, "count": int}],
    },
    "cost": {
        "median": float | None, "priced": int, "of": int, "estimated": bool, "measurement": float,
        "by_component": [{"component": str, "median": float | None, "total": float}],
        "by_size": [{"size": str, "median": float | None, "priced": int, "of": int}],
    },
    "merged_cost": {
        "median": float | None, "priced": int, "owner_recorded": int,
        "merged": int, "estimated": bool,
    },
    "expensive": [_FACTORY_PR],
    "scorers": _FACTORY_SCORERS,
    "improvements": _FACTORY_IMPROVEMENTS,
    "fix_rounds": [
        {"rounds": int, "merged": int, "closed": int, "open": int, "merge_rate": float | None},
    ],
    "role_notes": [{"role": str, "notes": int, "fixed": int}],
}  # fmt: skip
_FACTORY_RANGE = "from=2026-11-01&to=2026-11-08"

# What a change answers (`web/src/generated/Changed.ts`); a create or duplicate adds the new id.
# A route that answers `{}` on success is accepted too: the app reads each key only when present.
CHANGED = {"notice": str, "undo": str | None, "id?": str}
NOTHING = {"notice?": str, "undo?": str | None, "id?": str}


def _hand(spec: Any) -> Callable[[], Shape]:  # noqa: ANN401
    return lambda: shape_of_spec(spec)


_FINDING = {
    "id": str, "severity": str, "class": str, "file": str, "line": int, "text": str,
    "rule": str, "requirement": str, "state": str, "reason": str, "by": str,
}  # fmt: skip
_DIFF = {
    "files": [{"path": str, "lines": [{"kind": str, "number": int | None, "text": str}]}],
    "cut": bool,
    "limit": int,
    "branch": str,
    "default_branch": str,
}
_ROW = {
    "key": str,
    "state": str,
    "ticket": Any,  # a ticket reference, or null for a row of the board itself
    "actor": {"kind": str, "name": str},
    "line": str,
    "since": float,
    "until": float | None,
    "also": [Any],
    "pull": Any,
}
_TEAM_NOW = {
    "now": float,
    "today": float,
    "cycle": {"since": float, "from": str},
    "counts": Map(int),
    "groups": Map([_ROW]),
    "idle": [str],
    "paused": [str],
    "stages": [{"stage": str, "today": Any, "cycle": Any}],
    "peek": Map(Any),
}
_WINDOW = {"yes": int, "no": int, "unclear": int, "pass_rate": float | None}
_SCORER = {
    "repository": str, "name": str, "question": str, "stage": str, "sample": float,
    "threshold": int, "week": _WINDOW, "month": _WINDOW, "ticket": str,
}  # fmt: skip


@dataclass(frozen=True)
class Route:
    """One call of the web app. `shape` is None while no oracle for the answer exists yet."""

    method: str
    path: str
    owner: str
    shape: Callable[[], Shape] | None = None
    # The route as the tests call it against the sample world: path parameters and query string.
    example: str = ""


def _ticket(suffix: str = "") -> str:
    return f"/api/tickets/{{repository}}/{{id}}{suffix}"


_SAMPLE = "/api/tickets/sample/CF-1"

ROUTES: tuple[Route, ...] = (
    Route("GET", "/api/about", "about", _hand({"name": str, "version": str}), "/api/about"),
    Route("GET", "/api/board", "board", _board, "/api/board"),
    Route("GET", "/api/tickets", "board", _tickets, "/api/tickets"),
    Route("GET", _ticket(), "board", _ticket_page, _SAMPLE),
    Route("GET", "/api/archive", "board", _archive, "/api/archive"),
    Route("GET", "/api/repositories", "board", _hand([str]), "/api/repositories"),
    Route("POST", "/api/repositories", "repositories", _hand({"name": str, "path": str})),
    Route(
        "GET",
        "/api/repositories/{repository}/templates/{type}",
        "board",
        _hand({"text": str}),
        "/api/repositories/sample/templates/feature",
    ),
    Route("GET", "/api/views", "views", _hand([{"name": str, "query": str}]), "/api/views"),
    Route("POST", "/api/views", "views", _hand(NOTHING)),
    Route("DELETE", "/api/views/{name}", "views", _hand(NOTHING)),
    Route("POST", "/api/tickets", "tickets", _hand(CHANGED)),
    Route("POST", "/api/tickets/bulk", "tickets", _hand(CHANGED)),
    Route("PATCH", _ticket(), "tickets", _hand(CHANGED)),
    Route("DELETE", _ticket(), "ticket_writes", _hand(CHANGED)),
    Route("POST", _ticket("/move"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/duplicate"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/comments"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/messages"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/answers"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/links"), "tickets", _hand(CHANGED)),
    Route("DELETE", _ticket("/links/{kind}/{target}"), "tickets", _hand(CHANGED)),
    Route("POST", _ticket("/coordinator-undo"), "tickets", _hand(CHANGED)),
    Route("PUT", "/api/columns/{stage}/limit", "ticket_writes", _hand(CHANGED)),
    Route("POST", "/api/undo/{token}", "undo", _hand(CHANGED)),
    Route("GET", _ticket("/mock/{name}"), "tickets"),
    Route(
        "GET",
        _ticket("/findings"),
        "tickets",
        _hand({"findings": [_FINDING]}),
        _SAMPLE + "/findings",
    ),
    Route("POST", _ticket("/findings/{finding}"), "tickets", _hand(CHANGED)),
    Route("GET", _ticket("/diff"), "tickets", _hand(_DIFF), _SAMPLE + "/diff"),
    Route("GET", "/api/memory", "memory", _memory, "/api/memory"),
    Route("POST", "/api/memory", "memory", _hand(CHANGED)),
    Route("GET", "/api/memory/{repository}/{name}", "memory", _hand(_RECORD)),
    Route("PATCH", "/api/memory/{repository}/{id}", "memory", _hand(CHANGED)),
    Route("POST", "/api/memory/{repository}/{id}/approve", "memory", _hand(CHANGED)),
    Route("POST", "/api/memory/{repository}/{id}/dismiss", "memory", _hand(CHANGED)),
    Route("POST", "/api/memory/{repository}/{id}/merge", "memory", _hand(CHANGED)),
    Route("POST", "/api/memory/{repository}/{id}/retire", "memory", _hand(CHANGED)),
    Route("GET", "/api/inbox", "inbox", _inbox, "/api/inbox"),
    Route(
        "GET",
        "/api/inbox/count",
        "inbox",
        _hand({"count": int, "latest": str}),
        "/api/inbox/count",
    ),
    Route("GET", "/api/captures/{repository}/{id}/{tree}/{image}", "screens"),
    Route("POST", _ticket("/screens-approval"), "screens", _hand(CHANGED)),
    Route("POST", _ticket("/screens-changes"), "screens", _hand(CHANGED)),
    Route("GET", "/api/reply/{token}", "push"),
    Route("POST", "/api/hooks/tell", "hooks"),
    Route("POST", "/api/hooks/tell/confirm", "hooks"),
    Route("POST", "/api/hooks/permission", "hooks"),
    Route("POST", "/api/hooks/recall", "hooks"),
    Route("POST", "/api/reply/{token}", "push", _hand(CHANGED)),
    Route("POST", "/api/permissions/rules", "permissions", _hand(CHANGED)),
    Route("POST", "/api/permissions/{id}/{verdict}", "permissions", _hand(CHANGED)),
    Route("GET", "/api/sessions", "sessions", _sessions, "/api/sessions"),
    Route("GET", "/api/sessions/usage", "sessions", _usage, "/api/sessions/usage"),
    Route("GET", "/api/sessions/{session_id}/timeline", "sessions", _timeline),
    Route(
        "GET",
        "/api/sessions/{session_id}/calls/{seq}",
        "sessions",
        _hand({"tool": str, "input": Any, "output": Any}),
    ),
    Route("GET", "/api/usage", "runs"),
    Route("GET", "/api/runs/{run_id}/log", "runs"),
    Route("POST", "/api/runs/{id}/stop", "runs", _hand(CHANGED)),
    Route("GET", "/api/agents", "runs", _hand({"halted_at": float | None}), "/api/agents"),
    Route("POST", "/api/agents/stop", "runs", _hand(CHANGED)),
    Route("POST", "/api/agents/resume", "runs", _hand(CHANGED)),
    Route("POST", _ticket("/runs"), "runs", _hand(CHANGED)),
    Route("POST", _ticket("/reviews"), "runs", _hand(CHANGED)),
    Route("POST", _ticket("/split"), "runs", _hand(CHANGED)),
    Route("POST", _ticket("/checks"), "checks", _hand(CHANGED)),
    Route("POST", _ticket("/merge"), "delivery", _hand(CHANGED)),
    Route("POST", _ticket("/ship"), "delivery", _hand(CHANGED)),
    Route("GET", _ticket("/preview"), "previews"),
    Route("POST", _ticket("/preview"), "previews", _hand(CHANGED)),
    Route("DELETE", _ticket("/preview"), "previews", _hand(CHANGED)),
    Route("GET", "/api/flow", "metrics", _flow, "/api/flow"),
    Route("GET", "/api/gate-timings", "metrics"),
    Route(
        "GET",
        "/api/question-wait",
        "metrics",
        _hand({"answered": int, "median_seconds": float | None}),
        "/api/question-wait",
    ),
    # The page reads its ports at once; the contract tests share one database connection, so this
    # route's answer is checked through the browser tests, which run on a real server.
    Route("GET", "/api/team/now", "team", _hand(_TEAM_NOW)),
    Route("GET", "/api/team", "team"),
    Route("GET", "/api/scorers", "evals", _hand({"scorers": [_SCORER]}), "/api/scorers"),
    Route("GET", "/api/agent-definitions", "agents", _hand(_AGENT_LIST), "/api/agent-definitions"),
    Route(
        "GET",
        "/api/harnesses",
        "agents",
        _hand({"claude": bool, "codex": bool, "srt": bool}),
        "/api/harnesses",
    ),
    Route("POST", "/api/agent-definitions", "agents", _hand(CHANGED)),
    Route("PATCH", "/api/agent-definitions/{name}", "agents", _hand(CHANGED)),
    Route("DELETE", "/api/agent-definitions/{name}", "agents", _hand(CHANGED)),
    Route("POST", "/api/agent-definitions/{name}/move", "agents", _hand(CHANGED)),
    Route("POST", "/api/agent-definitions/{name}/context/restore", "agents", _hand(CHANGED)),
    Route("POST", "/api/agent-definitions/{name}/model-check", "agents"),
    Route("POST", "/api/agent-context/preview", "agents", _hand({"html": str})),
    Route("GET", "/api/claude-agents", "agents"),
    Route("GET", "/api/connections", "connections", _hand(_CONNECTION_LIST), "/api/connections"),
    Route("POST", "/api/connections", "connections", _hand(CHANGED)),
    Route("PATCH", "/api/connections/{name}", "connections", _hand(CHANGED)),
    Route("DELETE", "/api/connections/{name}", "connections", _hand(CHANGED)),
    Route(
        "GET",
        "/api/connection-status",
        "connections",
        _hand(_CONNECTION_STATUS),
        "/api/connection-status",
    ),
    Route(
        "GET",
        "/api/factory/dashboard",
        "factory",
        _hand(_FACTORY_DASHBOARD),
        f"/api/factory/dashboard?{_FACTORY_RANGE}",
    ),
    Route(
        "PUT",
        "/api/factory/tickets/{ticket_id}/owner-time",
        "factory",
        _hand({"pull_url": str, "active_minutes": int, "hourly_rate_usd": float}),
    ),
    Route(
        "GET",
        "/api/factory/runs",
        "factory",
        _hand(_FACTORY_RUNS),
        f"/api/factory/runs?{_FACTORY_RANGE}",
    ),
    Route(
        "GET",
        "/api/factory/prs/expensive",
        "factory",
        _hand({"prs": [_FACTORY_PR]}),
        f"/api/factory/prs/expensive?{_FACTORY_RANGE}&limit=3",
    ),
    Route(
        "GET",
        "/api/factory/scorers",
        "factory",
        _hand(_FACTORY_SCORERS),
        f"/api/factory/scorers?{_FACTORY_RANGE}",
    ),
    Route(
        "GET",
        "/api/factory/improvements",
        "factory",
        _hand(_FACTORY_IMPROVEMENTS),
        "/api/factory/improvements?limit=3",
    ),
)


# Owners whose module has not landed: their routes must not be served yet. Removing a name here is
# the one act that starts holding that module's routes to their shapes.
PENDING_OWNERS: frozenset[str] = frozenset()

# Served routes the web app does not call.
NOT_CALLED = frozenset(
    {("GET", "/api/health"), ("GET", "/api/ready"), ("GET", "/api/openapi.json")}
)

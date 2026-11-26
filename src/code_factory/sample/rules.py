"""The refusals that keep a sample command away from a real database."""

import ipaddress
import re
from pathlib import Path

from code_factory.platform.errors import BadRequestError
from code_factory.sample.models import SAMPLE_NAMES
from code_factory.sample.models.demo import DEMO_PRICES, DemoSession

DEFAULT_SCHEMA = "public"
TEST_DATABASE = re.compile(r"[a-z0-9_]+_test")
_REFUSED = (
    "the sample commands change a database wholesale and run only against a _test database on "
    "this machine"
)


def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_target(
    host: str | None, database: str | None, query: dict[str, object], schema: str
) -> None:
    """Refuse anything but a `_test` database on a loopback host, and the default schema.

    A query parameter can redirect the driver (`?database=`, `?host=`), so any is refused.
    """
    if query or not _loopback(host) or not TEST_DATABASE.fullmatch(database or ""):
        raise BadRequestError(f"{_REFUSED}; point CODE_FACTORY_DATABASE_URL at one")
    if schema == DEFAULT_SCHEMA:
        msg = (
            "the sample commands never touch the default schema: set CODE_FACTORY_DB_SCHEMA "
            "to a schema of its own, for example sample_1"
        )
        raise BadRequestError(msg)


def check_sample(name: str) -> str:
    """The sample's name, or a refusal naming the known ones."""
    if name not in SAMPLE_NAMES:
        msg = f"unknown sample {name}; the samples are: {', '.join(SAMPLE_NAMES)}"
        raise BadRequestError(msg)
    return name


def pull_url(repository: str, ticket: str) -> str:
    """The fictional forge address shown for a demo ticket."""
    return f"https://github.com/acme/{repository}/pull/{ticket.removeprefix('CF-')}"


def tool_input(tool: str, target: str, cwd: Path) -> dict[str, str]:
    """The input a demo session's tool call carries: a command, a pattern or a file under `cwd`."""
    if tool == "Bash":
        return {"command": target, "description": target}
    if tool == "Grep":
        return {"pattern": target}
    return {"file_path": str(cwd / target)}


def session_transcript(session: DemoSession, now: float) -> list[dict[str, object]]:
    """The assistant messages of a session with their tokens, and the runtime's cost report."""
    prices = DEMO_PRICES[session.model]
    records: list[dict[str, object]] = []
    cost = 0.0
    for at, tokens in enumerate(session.messages):
        usage = dict(
            zip(
                (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                ),
                tokens,
                strict=True,
            )
        )
        cost += sum(n * p for n, p in zip(tokens, prices, strict=True)) / 1_000_000
        message = {"id": f"msg_{session.session_id}_{at}", "model": session.model, "usage": usage}
        records.append({"type": "assistant", "message": message})
    started = now - 20 * 60
    records.append(
        {
            "type": "cost-state",
            "totalCostUSD": round(cost, 6),
            "startTime": int(started * 1000),
            "totalDuration": int((now - started) * 1000),
        }
    )
    return records

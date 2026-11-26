"""The run key request and what counts as the provider having made one."""

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import SecretStr

from code_factory.broker.models import RunKeyMade
from code_factory.broker.rules.headers import MIN_SECRET

OK = 2


def expires_text(at: datetime) -> str:
    """UTC, whole seconds, `Z`: the form the provider documents."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_key_request(run_id: str, cap_usd: Decimal, expires_at: datetime) -> dict[str, object]:
    """The body that makes a key limited to the run's cap and bounded by its time."""
    return {
        "name": f"code-factory run {run_id}",
        "limit": float(cap_usd),
        "expires_at": expires_text(expires_at),
    }


def run_key_made(status: int, body: object) -> RunKeyMade | None:
    """The key the provider made: only a 2xx with a string `key` of at least 8 characters counts."""
    if status // 100 != OK or not isinstance(body, dict):
        return None
    key = body.get("key")
    if not isinstance(key, str) or len(key) < MIN_SECRET:
        return None
    data = body.get("data")
    made = data.get("hash") if isinstance(data, dict) else None
    return RunKeyMade(id=made if isinstance(made, str) else "", key=SecretStr(key))

"""A run's OpenTelemetry environment and its iteration cap."""

import hashlib
import re
from typing import override

from pydantic import SecretBytes

DEFAULT_ITERATIONS = 12
LOGS_PATH = "/v1/logs"
TOKEN_HEADER = "x-code-factory-token"  # noqa: S105  # a header name
# Printable ASCII except `"`, `,`, `;` and `\`.
_FORBIDDEN = re.compile(r"[^\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]")


class Receiver:
    """Where the board receives run telemetry, and the secret its runs' tokens are made from."""

    def __init__(self, address: str, secret: SecretBytes) -> None:
        self.address = address
        self._secret = secret

    def token(self, run_id: str) -> str:
        """The token run `run_id` sends: SHA-256 of the secret and the id, in hex."""
        digest = hashlib.sha256(self._secret.get_secret_value() + run_id.encode())
        return digest.hexdigest()

    @override
    def __repr__(self) -> str:
        """The address only: the secret is never shown."""
        return f"Receiver(address={self.address!r})"


def max_iterations(value: object) -> int:
    """The loop's iteration cap: a whole number above 0, else 12; a bool is not a number."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return DEFAULT_ITERATIONS


def telemetry_env(  # noqa: PLR0913  # the facts of one run, named
    *,
    endpoint: str | None,
    protocol: str | None,
    ticket_id: str,
    run_id: str,
    stage: str,
    repository: str,
    receiver: Receiver | None,
) -> dict[str, str]:
    r"""The variables that turn a run's telemetry on, in order; none with neither destination.

    Metrics and events go to the repository's `endpoint`, the events to the board's `receiver`
    when there is one (claude sends a signal to one endpoint only), the run's token on those
    alone. Attribute values lose every byte outside `0x21..0x7e` and `",;\\`.
    """
    endpoint = endpoint or None
    if endpoint is None and receiver is None:
        return {}
    tags = {"ticket": ticket_id, "run": run_id, "stage": stage, "repository": repository}
    attributes = ",".join(
        f"code_factory.{key}={_FORBIDDEN.sub('_', value)}" for key, value in tags.items()
    )
    env = {"CLAUDE_CODE_ENABLE_TELEMETRY": "1"}
    if endpoint is not None:
        env["OTEL_METRICS_EXPORTER"] = "otlp"
    env["OTEL_LOGS_EXPORTER"] = "otlp"
    if endpoint is not None:
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
        env["OTEL_EXPORTER_OTLP_PROTOCOL"] = protocol or "grpc"
    if receiver is not None:
        env["OTEL_EXPORTER_OTLP_LOGS_PROTOCOL"] = "http/json"
        env["OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"] = f"{receiver.address}{LOGS_PATH}"
        env["OTEL_EXPORTER_OTLP_LOGS_HEADERS"] = f"{TOKEN_HEADER}={receiver.token(run_id)}"
    env["OTEL_RESOURCE_ATTRIBUTES"] = attributes
    return env

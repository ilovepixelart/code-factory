"""What the broker module's service takes and answers, and the shapes of what it reads elsewhere."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from code_factory.platform.errors import CodeFactoryError

KEY_STATES = ("none", "making", "made", "refused")
CODEX_LOGIN = "codex-login"
ANTHROPIC = "anthropic"
CAP_LIMIT = Decimal(1_000_000)
TOKEN_HEADER = "x-code-factory-token"  # noqa: S105  # a header name, not a secret


class TokenRefusedError(CodeFactoryError):
    """The token is not a live run token: malformed, unknown, ended or expired alike."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class BrokerConnection(_Frozen):
    """A model connection as the broker reads it: names of keys, never keys."""

    name: str
    kind: str
    base_url: str
    key_name: str = ""
    management_key_name: str | None = None

    @field_validator("management_key_name")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class CodexLogin(_Frozen):
    """The owner's ChatGPT login, held for one request."""

    access_token: SecretStr
    account_id: str


class BrokerEndpoints(_Frozen):
    """Where a run reaches the broker."""

    proxy_url: str
    telemetry_url: str


class IssuedToken(_Frozen):
    """What a run is started with; the token exists only here."""

    token: SecretStr
    proxy_url: str
    telemetry_url: str
    environment: dict[str, Annotated[str | SecretStr, Field(union_mode="left_to_right")]]


class TokenRow(_Frozen):
    """A `broker_tokens` row: the digest of the token, never the token or a key."""

    id: int
    digest: str
    run_id: str
    connection: str | None
    cap_usd: Decimal | None
    key_state: str
    run_key_id: str | None
    created_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    key_delete_failed_at: datetime | None
    key_delete_error: str | None
    key_state_at: datetime | None


class TokenGrant(_Frozen):
    """What a live token stands for."""

    run_id: str
    connection: str | None
    cap_usd: Decimal | None
    key_state: str
    expires_at: datetime


class TokenInfo(_Frozen):
    """A token row as `status` shows it: no digest, no token, no key."""

    run_id: str
    connection: str | None
    cap_usd: Decimal | None
    key_state: str
    ended: bool
    expires_at: datetime
    key_delete_error: str | None


class BrokerStatus(_Frozen):
    """Counts for the command line and the health detail."""

    listening: bool
    port: int | None
    live_tokens: int
    keys_held: int
    keys_pending_delete: int


class SweepReport(_Frozen):
    """What one sweep pass did."""

    deleted: int = 0
    failed: int = 0
    dropped_tokens: int = 0


class RunKeyMade(_Frozen):
    """A run key the provider made; `id` is empty when the provider named none."""

    id: str
    key: SecretStr


class DeleteResult(_Frozen):
    """The outcome of deleting a run key at the provider; `why` is one fixed sentence."""

    ok: bool
    why: str = ""


@dataclass(frozen=True)
class Target:
    """What a request may be sent to: the path (with its query) joined to the connection's base."""

    path: str


@dataclass(frozen=True)
class Refusal:
    """A request the broker does not send, with the sentence the log keeps."""

    reason: str


@dataclass(frozen=True)
class Connect:
    """A `CONNECT` the run proxy accepts: the exact `host:port` asked for."""

    target: str


@dataclass(frozen=True)
class ConnectRefusal:
    """A `CONNECT` head the run proxy answers with `status` (405 or 403), or drops (0)."""

    status: int
    reason: str


class KeyCreated(_Frozen):
    """The outcome of asking the provider for a run key.

    `answered` is whether the provider said anything at all: a hung call may have made a key, a
    refusal did not.
    """

    made: RunKeyMade | None
    answered: bool


WHY_REFUSED = "the provider refused it"
WHY_SILENT = "the provider did not answer"
WHY_GONE = "its connection is gone"
WHY_NO_KEY = "its management key is not set"
WHY_ADDRESS = "its address cannot be read"
WHY_ID = "its key id cannot be sent"

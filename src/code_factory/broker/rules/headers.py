"""Headers: what is never sent on, which credential goes, and what comes back."""

from collections.abc import Iterable, Sequence

NOT_SENT_ON = frozenset(
    {
        "host",
        "authorization",
        "x-api-key",
        "proxy-authorization",
        "connection",
        "keep-alive",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "cookie",
        "cookie2",
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-real-ip",
        "chatgpt-account-id",
    }
)
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "set-cookie",
    }
)
MIN_SECRET = 8


def outbound_headers(
    incoming: Sequence[tuple[str, str]],
    credential: tuple[str, str],
    extra: Sequence[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    """The headers to send: the run's own minus `NOT_SENT_ON`, then the one credential."""
    kept = [(name, value) for name, value in incoming if name.lower() not in NOT_SENT_ON]
    return [*kept, credential, *extra]


def credential_header(kind: str, key: str) -> tuple[str, str]:
    """The header that carries the key: `x-api-key` for anthropic, a bearer for every other."""
    if kind == "anthropic":
        return ("x-api-key", key)
    return ("authorization", f"Bearer {key}")


def response_headers(
    upstream: Iterable[tuple[str, str]], secrets: Iterable[str]
) -> list[tuple[str, str]]:
    """The provider's headers to pass on: no hop-by-hop, no cookie, none holding a secret."""
    held = [secret for secret in secrets if len(secret.encode()) >= MIN_SECRET]
    return [
        (name, value)
        for name, value in upstream
        if name.lower() not in _HOP_BY_HOP and not any(secret in value for secret in held)
    ]

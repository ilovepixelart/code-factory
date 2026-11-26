"""What a request may ask for: refused rather than normalised, before any parser sees it."""

from urllib.parse import unquote

from code_factory.broker.models import CODEX_LOGIN, Refusal, Target

MAX_TARGET = 4096
MAX_DECODES = 4
_PREFIX = "/v1/"
_MANAGEMENT = "/v1/keys"
_CODEX_PATH = "/v1/responses"
_REFUSED = Refusal("the target is not one the key broker sends")


def _printable(text: str) -> bool:
    """Visible ASCII only: no space, control character or byte a parser could read differently."""
    return text.isascii() and all("!" <= char <= "~" for char in text)


def _malformed(raw_target: str) -> bool:
    return (
        len(raw_target) > MAX_TARGET
        or not raw_target.startswith("/")
        or not _printable(raw_target)
        or "#" in raw_target
    )


def _decoded(path: str) -> str | None:
    """The path with every layer of percent encoding removed; `None` when it never settles."""
    for _ in range(MAX_DECODES):
        after = unquote(path)
        if after == path:
            return path
        path = after
    return None


def _hostile(path: str) -> bool:
    """Whether the path, however it is decoded, climbs, doubles a slash or smuggles a separator."""
    if "//" in path:
        return True
    plain = _decoded(path)
    if plain is None or not plain.isprintable() or "\\" in plain or "//" in plain:
        return True
    return any(part in {".", ".."} for part in plain.split("/"))


def _reaches_management(path: str) -> bool:
    plain = _decoded(path)
    return plain is None or plain.lower().startswith(_MANAGEMENT)


def codex_request_ok(method: str, raw_target: str) -> bool:
    """Whether the request is exactly `POST /v1/responses`, a query kept."""
    return method == "POST" and raw_target.partition("?")[0] == _CODEX_PATH


def request_target(kind: str, method: str, raw_target: str) -> Target | Refusal:
    """The path to send a request to, or why it is refused.

    `raw_target` is the request line's target, untouched. A keyed kind takes a path under `/v1/`
    that is not the key management surface; the codex login takes exactly `POST /v1/responses`,
    sent without its `/v1`.
    """
    path, question, query = raw_target.partition("?")
    if _malformed(raw_target) or _hostile(path):
        return _REFUSED
    if kind == CODEX_LOGIN:
        if not codex_request_ok(method, raw_target):
            return _REFUSED
        return Target(f"/responses{question}{query}")
    if not path.startswith(_PREFIX) or len(path) == len(_PREFIX) or _reaches_management(path):
        return _REFUSED
    return Target(raw_target)

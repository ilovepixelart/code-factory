"""The run proxy's CONNECT head: one method, one exact target."""

import re
from collections.abc import Sequence

from code_factory.broker.models import Connect, ConnectRefusal

MAX_HEAD = 8192
_END = b"\r\n\r\n"
_VERSION = re.compile(r"HTTP/1\.[01]")
_PORT = re.compile(r"[1-9][0-9]{0,4}")
_HOST = re.compile(r"[a-z0-9.-]+")
MAX_PORT = 65535
DROP = ConnectRefusal(0, "the request head is not one request line and headers")


def allowed_hosts(model_host: str) -> list[str]:
    """What a container run may reach: its connection's checked `host:port`."""
    return [model_host]


def _allowed(target: str, allowed: Sequence[str]) -> bool:
    host, colon, port = target.rpartition(":")
    return (
        bool(colon)
        and _HOST.fullmatch(host) is not None
        and _PORT.fullmatch(port) is not None
        and int(port) <= MAX_PORT
        and target in allowed
    )


def parse_connect(head: bytes, allowed: Sequence[str]) -> Connect | ConnectRefusal:
    """The target of a `CONNECT` head when it is on the allowed list, else why not.

    The head ends at its first blank line and is at most 8 KiB; a method other than CONNECT is 405;
    the target is the exact lowercase `host:port` of an allowed entry, anything else is 403.
    """
    if len(head) > MAX_HEAD or not head.endswith(_END) or head.count(_END) != 1:
        return DROP
    line = head.decode("latin-1").split("\r\n", 1)[0]
    method, first, rest = line.partition(" ")
    target, second, version = rest.rpartition(" ")
    if not first or not second or _VERSION.fullmatch(version) is None:
        return DROP
    if method != "CONNECT":
        return ConnectRefusal(405, "only CONNECT is answered")
    if not _allowed(target.lower(), allowed):
        return ConnectRefusal(403, "this host is not on the allowed list")
    return Connect(target.lower())

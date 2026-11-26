"""What makes a value acceptable: the pure checks the value kinds and the rules share."""

import re
from collections.abc import Sequence

INTAKE_KEY_PREFIX = "CODE_FACTORY_INTAKE_"
DOCUMENTS = ("requirements", "spec", "uat")
LINEAR_API = "https://api.linear.app/graphql"
SLACK_API = "https://slack.com/api"

_PREFIX = re.compile(r"[A-Z][A-Z0-9]{0,9}")
_KEY_NAME = re.compile(re.escape(INTAKE_KEY_PREFIX) + r"[A-Z0-9_]+")
_MOST_PORT = 65535
_SPACE = 32  # the first printable character
_LOCAL_HOSTS = ("localhost", "127.0.0.1")
_OWN_HOSTS = {"linear": "api.linear.app", "slack": "slack.com"}


def is_glob(pattern: str) -> bool:
    """Whether `pattern` is a path pattern: not blank, and no `[` left unclosed.

    `fnmatch` takes an unclosed `[` as a literal, and a mistyped class never matches what it
    meant. A class is `[`, an optional `!`, an optional `]`, then anything up to the closing `]`.
    """
    if not pattern.strip():
        return False
    i = 0
    while i < len(pattern):
        if pattern[i] == "[":
            j = i + 1
            if pattern[j : j + 1] == "!":
                j += 1
            if pattern[j : j + 1] == "]":
                j += 1
            closing = pattern.find("]", j)
            if closing < 0:
                return False
            i = closing
        i += 1
    return True


def is_prefix(text: str) -> bool:
    """Whether `text` can prefix a ticket id: 1 to 10 capitals or digits, a capital first."""
    return _PREFIX.fullmatch(text) is not None


def _is_port(text: str) -> bool:
    return text.isascii() and text.isdigit() and 0 < int(text) <= _MOST_PORT


def host_port(entry: str) -> bool:
    """Whether `entry` is `<host>:<port>`: a host that is no `*`, a port from 1 to 65535.

    A host named without a port admits every port of it, and `*` admits every host.
    """
    host, separator, port = entry.rpartition(":")
    return (
        bool(separator)
        and bool(host)
        and host != "*"
        and "/" not in host
        and " " not in host
        and _is_port(port)
    )


def key_name(name: str) -> bool:
    """Whether `name` may name a tracker key: the intake prefix, then capitals, digits or `_`."""
    return _KEY_NAME.fullmatch(name) is not None


def _authority(address: str) -> tuple[bool, str] | None:
    """`(is_https, host)` of an address with an http or https scheme and no userinfo."""
    if any(c.isspace() or c == "\\" or ord(c) < _SPACE for c in address):
        return None
    scheme, separator, rest = address.partition("://")
    if not separator or scheme not in {"http", "https"}:
        return None
    authority = str(re.split(r"[/?#]", rest, maxsplit=1)[0])
    if "@" in authority:
        return None
    host, _, port = authority.rpartition(":") if ":" in authority else (authority, "", "")
    if ":" in authority and not _is_port(port):
        return None
    return scheme == "https", host.rstrip(".").lower()


def tracker_allowed(tracker: str, address: str) -> bool:
    """Whether a `tracker`'s key may be sent to `address`.

    https to the tracker's own host, or http or https to this machine; an address holding a
    user is none.
    """
    parsed = _authority(address)
    if parsed is None:
        return False
    secure, host = parsed
    if host in _LOCAL_HOSTS:
        return True
    return secure and _own_host(tracker, host)


def _own_host(tracker: str, host: str) -> bool:
    """Whether `host` is the host of `tracker`: Linear's API, Slack, or one Atlassian Cloud site."""
    if tracker == "jira":
        site = host.removesuffix(".atlassian.net")
        return site != host and bool(site) and "." not in site
    return host == _OWN_HOSTS.get(tracker)


def documents_entry(value: object) -> Sequence[str] | None:
    """The documents of a `[documents]` entry in canonical order, or None when it is not one.

    An entry is a list of distinct names from `DOCUMENTS` that holds `requirements`.
    """
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    names = set(value)
    if len(names) != len(value) or not names <= set(DOCUMENTS) or "requirements" not in names:
        return None
    return tuple(name for name in DOCUMENTS if name in names)

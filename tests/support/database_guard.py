"""The rule that tests touch only a database whose name ends in `_test`, on this machine.

The URL is parsed the way SQLAlchemy parses it, because the asyncpg dialect lets query parameters
(`?database=`, `?host=`, ...) override the path and host: reading the path alone approves URLs
that connect elsewhere. Every query parameter is refused for that reason.
"""

import ipaddress
import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

TEST_DATABASE_PATTERN = re.compile(r"[a-z0-9_]+_test")
LOOPBACK_NAMES = frozenset({"localhost"})


class UnsafeDatabaseError(Exception):
    """The configured database is not a test database on this machine."""


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_test_database(url: str) -> None:
    """Raise `UnsafeDatabaseError` unless the URL is a `_test` database on a loopback host.

    Messages name the database or the offending parameter and never the URL, which holds the
    password.
    """
    try:
        parsed = make_url(url)
    except ArgumentError:
        msg = "refusing to run tests: the database URL cannot be parsed"
        raise UnsafeDatabaseError(msg) from None
    if parsed.query:
        names = ", ".join(sorted(parsed.query))
        msg = (
            f"refusing to run tests: the database URL has query parameter(s) {names}, which "
            "can change where the driver connects; put host, port and database in the URL itself"
        )
        raise UnsafeDatabaseError(msg)
    if not _is_loopback(parsed.host):
        msg = (
            f"refusing to run tests against host {parsed.host!r}: tests run only against a "
            "loopback host (127.0.0.1, ::1, localhost)"
        )
        raise UnsafeDatabaseError(msg)
    name = parsed.database or ""
    if not TEST_DATABASE_PATTERN.fullmatch(name):
        msg = (
            f"refusing to run tests against database {name!r}: tests run only against a "
            f"database whose name matches {TEST_DATABASE_PATTERN.pattern!r} (code_factory_test)"
        )
        raise UnsafeDatabaseError(msg)

"""The database password from the macOS keychain, for a database URL that leaves it out.

A board run by launchd has no shell to export the URL with the password in it; the keychain item
`code-factory-postgres` (account: the database user) holds it instead, never a file.
"""

import subprocess
from pathlib import Path

SERVICE = "code-factory-postgres"
SECURITY = Path("/usr/bin/security")
LOOKUP_S = 10.0


def database_password(account: str) -> str | None:
    """The keychain's password of `account` for the board's database; None when there is none."""
    if not SECURITY.is_file():
        return None
    try:
        done = subprocess.run(  # noqa: S603  # a fixed program by absolute path, no shell
            [str(SECURITY), "find-generic-password", "-a", account, "-s", SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=LOOKUP_S,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    password = done.stdout.rstrip("\n")
    return password if done.returncode == 0 and password else None

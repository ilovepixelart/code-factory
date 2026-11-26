"""When a release is verified, and the bug a failure files."""

from datetime import datetime, timedelta

from code_factory.checks.models import BugDraft, ReleaseRef

DEFAULT_WATCH_DAYS = 7
INTERVAL = timedelta(hours=1)
TAIL_LINES = 40


def verify_due(
    command: str | None,
    newest: ReleaseRef | None,
    now: datetime,
    last_at: datetime | None,
    watch_days: int | None,
) -> bool:
    """Whether `[release] verify` is due: a command, a release inside its window, an hour since."""
    days = DEFAULT_WATCH_DAYS if watch_days is None else watch_days
    if command is None or not command or newest is None or days == 0:
        return False
    if now - newest.at > timedelta(days=days):
        return False
    return last_at is None or now - last_at >= INTERVAL


def log_tail(text: str, lines: int = TAIL_LINES) -> str:
    """The last `lines` lines of `text`."""
    return "\n".join(text.splitlines()[-lines:])


def verify_bug(
    release: ReleaseRef, command: str, code: int, log: str, tail_masked: str
) -> BugDraft:
    """The bug filed for a release that fails its verification."""
    description = (
        f"Filed by the board: `{command}` ended with exit code {code} while release "
        f"{release.version} was inside its verification window. Log: {log}\n\n"
        f"```\n{tail_masked}\n```"
    )
    return BugDraft(
        title=f"Release {release.version} fails its verification",
        type="bug",
        labels=["release"],
        priority="high",
        caused_by=list(release.tickets),
        description=description,
    )

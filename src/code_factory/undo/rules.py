"""The undo window and its tokens. Pure: the clock is an argument."""

import secrets
from datetime import datetime, timedelta

WINDOW = timedelta(seconds=30)
# An entry is claimed or refused at its expiry; the sweep only removes what nobody claimed.
SWEEP_AFTER = timedelta(seconds=60)


def new_token() -> str:
    """32 hex characters from the system's secure random source."""
    return secrets.token_hex(16)


def expires_at(offered: datetime) -> datetime:
    """When an entry offered at `offered` stops being claimable."""
    return offered + WINDOW


def undo_live(expiry: datetime, now: datetime) -> bool:
    """Live while `now <= expiry`: exactly at the expiry still counts."""
    return now <= expiry


def sweep_cutoff(now: datetime) -> datetime:
    """Entries that expired before this are deleted by the sweep."""
    return now - SWEEP_AFTER

"""Names for trees and contents."""

import hashlib


def short_digest(text: str) -> str:
    """The first 16 hex characters of the SHA-256 of `text`."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def tree_name(commit: str, status: str, changes: str) -> str:
    """Name a tree by its commit, its status and its changes."""
    return short_digest(f"{commit}\0{status}\0{changes}")

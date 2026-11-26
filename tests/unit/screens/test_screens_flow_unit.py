"""A capture waits on the Inbox, its images are served, and the owner approves or sends it back."""

from code_factory.screens.rules import waiting


def test_only_an_unanswered_latest_capture_waits() -> None:
    first, second = {"tree": "aaaaaaa"}, {"tree": "bbbbbbb"}
    assert waiting([("capture", first)]) == first
    assert waiting([("capture", first), ("capture_approved", first)]) is None
    assert waiting([("capture", first), ("capture_approved", first), ("capture", second)]) == second
    assert waiting([("capture", first), ("capture_changes", {"tree": "aaaaaaa"})]) is None
    assert waiting([]) is None

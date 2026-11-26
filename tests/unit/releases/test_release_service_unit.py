"""Releases through the release service, against the test database.

The notes layout and the version form are the previous implementation's (`release_notes_are_
drafted_once`, `a_version_is_three_numbers`); the states and refusals are the commands spec's
`ReleaseService` table.
"""

from code_factory.releases.service import ReleaseService


def test_the_version_and_tag_rules_are_the_services() -> None:
    assert ReleaseService.is_version("1.2.3")
    assert not ReleaseService.is_version("1.2.3-rc.1")
    assert ReleaseService.newest_tag(["v0.9.0", "v0.10.0", "v1.0.0-rc.1", "nightly"]) == "v0.10.0"

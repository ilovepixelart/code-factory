"""The YAML edge reads only the keys the rules use, under a size cap, in a worker thread."""

from code_factory.settings.adapters import lock_packages, workspace_lists

WORKSPACE = """\
auditConfig:
  ignoreGhsas:
    - GHSA-aaaa-bbbb-cccc
audit:
  ignore:
    - GHSA-dddd-eeee-ffff
minimumReleaseAgeExclude:
  - left-pad@1.3.0
  - '@scope/*'
other: 1
"""

# pnpm 12 writes its own environment's document, then the project's.
LOCK = """\
---
lockfileVersion: '9.0'

packages:

  '@pnpm/exe@12.14.0':
    resolution: {integrity: x}

---
lockfileVersion: '9.0'

packages:

  left-pad@1.3.0:
    resolution: {integrity: y}
"""


async def test_a_workspace_gives_its_ignores_and_age_exclusions() -> None:
    found = await workspace_lists(WORKSPACE)
    assert found is not None
    assert found.ignores == ["GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff"]
    assert found.excludes == ["left-pad@1.3.0", "@scope/*"]


async def test_an_empty_or_unrelated_workspace_lists_nothing() -> None:
    for text in ("", "minimumReleaseAge: 20160\n", "- a\n- b\n"):
        found = await workspace_lists(text)
        assert found is not None
        assert (found.ignores, found.excludes) == ([], [])


async def test_a_workspace_that_is_not_yaml_is_none() -> None:
    assert await workspace_lists("a: [1, 2\n") is None


async def test_a_workspace_past_the_cap_is_none() -> None:
    assert await workspace_lists("a: " + "x" * (2 * 1024 * 1024)) is None
    assert await workspace_lists("a: " + "x" * 1000) is not None


async def test_a_lockfile_gives_the_package_keys_of_every_document() -> None:
    assert await lock_packages(LOCK) == frozenset({"@pnpm/exe@12.14.0", "left-pad@1.3.0"})


async def test_a_lockfile_without_packages_or_with_bad_yaml() -> None:
    assert await lock_packages("lockfileVersion: '9.0'\n") == frozenset()
    assert await lock_packages("a: [1\n") is None


async def test_yaml_tags_are_not_constructed() -> None:
    assert await workspace_lists("a: !!python/object/apply:os.system ['true']\n") is None

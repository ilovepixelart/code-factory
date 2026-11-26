"""What the key broker reads of the agents module: a connection by name, its checked address,
and the codex login read fresh."""

from agents_support import FakeStore, store_fixture  # noqa: F401


def test_the_store_fixture_is_used(store: FakeStore) -> None:
    assert store.keys == {}

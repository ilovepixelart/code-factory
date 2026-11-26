"""The parsed configs of the newest repositories, each valid for one version of its file."""

from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from code_factory.settings.adapters.files import FileKey
from code_factory.settings.models.config import RepositoryConfig

CACHE_ROOTS = 64


class _Cached(NamedTuple):
    key: FileKey
    config: RepositoryConfig


class ConfigCache:
    """At most `CACHE_ROOTS` roots, the least recently used one leaving first."""

    def __init__(self) -> None:
        self._items: OrderedDict[Path, _Cached] = OrderedDict()

    def get(self, root: Path, key: FileKey) -> RepositoryConfig | None:
        """The config remembered for `root` while its file still has `key`."""
        cached = self._items.get(root)
        if cached is None or cached.key != key:
            return None
        self._items.move_to_end(root)
        return cached.config

    def put(self, root: Path, key: FileKey, config: RepositoryConfig) -> None:
        """Remember `config` for `root`, dropping the oldest roots past the limit."""
        self._items[root] = _Cached(key, config)
        self._items.move_to_end(root)
        while len(self._items) > CACHE_ROOTS:
            self._items.popitem(last=False)

    def drop(self, root: Path) -> None:
        """Forget `root`."""
        self._items.pop(root, None)

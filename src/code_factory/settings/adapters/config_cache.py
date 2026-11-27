"""The parsed configs of the newest repositories, each valid for one version of its file."""

from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from code_factory.settings.models.config import RepositoryConfig

CACHE_ROOTS = 64


class _Cached(NamedTuple):
    text: str
    config: RepositoryConfig


class ConfigCache:
    """At most `CACHE_ROOTS` roots, the least recently used one leaving first."""

    def __init__(self) -> None:
        self._items: OrderedDict[Path, _Cached] = OrderedDict()

    def get(self, root: Path, text: str) -> RepositoryConfig | None:
        """The config remembered for `root` while its contents are unchanged."""
        cached = self._items.get(root)
        if cached is None or cached.text != text:
            return None
        self._items.move_to_end(root)
        return cached.config

    def put(self, root: Path, text: str, config: RepositoryConfig) -> None:
        """Remember `config` for `root`, dropping the oldest roots past the limit."""
        self._items[root] = _Cached(text, config)
        self._items.move_to_end(root)
        while len(self._items) > CACHE_ROOTS:
            self._items.popitem(last=False)

    def drop(self, root: Path) -> None:
        """Forget `root`."""
        self._items.pop(root, None)

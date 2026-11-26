"""Run keys held in memory only, never in a row, a log or a repr."""

from typing import override

from pydantic import SecretStr


class RunKeyVault:
    """The run keys of this process by run id."""

    def __init__(self) -> None:
        self._keys: dict[str, SecretStr] = {}

    def get(self, run_id: str) -> SecretStr | None:
        """The run's key, if this process made it."""
        return self._keys.get(run_id)

    def put(self, run_id: str, key: SecretStr) -> None:
        """Hold the run's key."""
        self._keys[run_id] = key

    def drop(self, run_id: str) -> None:
        """Forget the run's key."""
        self._keys.pop(run_id, None)

    def __len__(self) -> int:
        """How many keys are held."""
        return len(self._keys)

    @override
    def __repr__(self) -> str:
        """The run ids only."""
        return f"RunKeyVault(runs={sorted(self._keys)})"

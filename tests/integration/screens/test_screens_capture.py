"""A capture refuses before it starts anything when Node cannot be found."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from code_factory.platform.errors import UnavailableError
from code_factory.screens.adapters import capture


async def test_a_capture_without_node_on_the_path_is_refused_with_how_to_repair_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # a trusted folder that holds no node

    with pytest.raises(UnavailableError) as refused:
        await capture("http://127.0.0.1:4000", tmp_path, ["/inbox"], SecretStr("s"))

    assert str(refused.value) == "the capture tool needs Node: install Node 26 or later"

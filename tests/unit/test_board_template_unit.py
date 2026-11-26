"""The `board_ids` fixture hands each test the `board` sample as `SampleService.load` leaves it."""

import os
import re


def test_an_xdist_worker_runs_in_a_schema_of_its_own() -> None:
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker is None:
        return
    assert re.fullmatch(rf"test_[0-9a-f]{{32}}_{worker}", os.environ["CODE_FACTORY_DB_SCHEMA"])

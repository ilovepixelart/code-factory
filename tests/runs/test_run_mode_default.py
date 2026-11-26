"""A run asks nothing by default: every run is in the sandbox, which holds the network, the
secrets and the writes outside the tree, so a prompt only stalls the work."""

from code_factory.runs.models import StartOptions
from code_factory.runs.routes import StartBody


def test_a_plain_start_skips_prompts() -> None:
    assert StartOptions().permissions == "bypassPermissions"
    assert StartBody().permissions == "bypassPermissions"


def test_the_owner_may_still_ask_for_accept_edits() -> None:
    assert StartBody.model_validate({"permissions": "acceptEdits"}).permissions == "acceptEdits"


def test_skip_prompts_is_a_mode_the_start_route_takes() -> None:
    body = StartBody.model_validate({"permissions": "bypassPermissions"})
    assert body.options().permissions == "bypassPermissions"


def test_loop_asks_for_a_looping_run() -> None:
    assert StartBody.model_validate({"loop": True}).options().looping is True
    assert StartBody().options().looping is False

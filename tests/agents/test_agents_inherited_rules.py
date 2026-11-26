"""Which variables a run does not inherit, worked by hand from the lists."""

import pytest

from code_factory.agents.rules.inherited import (
    left_out,
    uncontained_left_out_of,
    unreadable_names,
)

CREDENTIALS = [
    "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GH_TOKEN", "GITHUB_TOKEN",
    "SSH_AUTH_SOCK", "MY_PRIVATE_KEY", "FOO_AUTH", "NPM_TOKEN", "MY_SECRET", "GIT_ASKPASS",
    "GIT_CONFIG_KEY_0", "CLAUDE_CODE_PLUGIN_DIRS", "STRIPE_API_KEY", "SENTRY_DSN",
]  # fmt: skip


@pytest.mark.parametrize("runtime", ["claude", "codex"])
def test_outside_the_sandbox_no_credential_of_any_name_is_inherited(runtime: str) -> None:
    dropped = uncontained_left_out_of(runtime, [*CREDENTIALS, "PATH", "HOME", "LANG"])
    assert set(CREDENTIALS) <= set(dropped)
    assert not {"PATH", "HOME", "LANG"} & set(dropped)


def test_outside_the_sandbox_claude_keeps_its_own_login_and_another_runtime_does_not() -> None:
    names = ["PATH", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"]
    assert uncontained_left_out_of("claude", names) == []
    assert uncontained_left_out_of("codex", names) == names[1:]


def test_outside_the_sandbox_a_name_the_lists_never_heard_of_is_not_inherited() -> None:
    assert uncontained_left_out_of("claude", ["PATH", "ZZ_UNHEARD_OF"]) == ["ZZ_UNHEARD_OF"]


def test_in_the_sandbox_only_the_base_variables_and_claudes_own_survive() -> None:
    names = ["PATH", "HOME", "FOO", "ANTHROPIC_API_KEY", "HTTPS_PROXY", "TZ"]
    assert left_out("claude", names) == ["FOO"]
    assert left_out("codex", names) == ["FOO", "ANTHROPIC_API_KEY", "HTTPS_PROXY"]


def test_a_name_that_is_not_utf8_is_always_dropped() -> None:
    assert unreadable_names([b"OK", b"BAD\xff", "é".encode()]) == [b"BAD\xff"]

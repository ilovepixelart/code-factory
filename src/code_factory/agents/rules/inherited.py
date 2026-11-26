"""Which of the board's environment variables a run does not inherit."""

from collections.abc import Iterable

from code_factory.agents.rules.settings import RUNTIME_VARIABLES

# What a process contained in srt keeps: where programs and home are, the user, the shell, the
# terminal, the locale and the time zone. A list of denied names cannot name every key, so the
# rest is left out, in the sandbox or not.
BASE_VARIABLES = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TERM",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
)
# What a claude run keeps beside the base ones and its keys: where its requests go, its
# configuration folder (which also names its stored login), and the proxy and certificates its
# requests pass through.
CLAUDE_VARIABLES = (
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CONFIG_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "NODE_EXTRA_CA_CERTS",
)


def unreadable_names(names: Iterable[bytes]) -> list[bytes]:
    """Of the board's variable names, those that are not UTF-8: no list can name them."""
    unreadable = []
    for name in names:
        try:
            name.decode("utf-8")
        except UnicodeDecodeError:
            unreadable.append(name)
    return unreadable


def uncontained_left_out_of(runtime: str, names: Iterable[str]) -> list[str]:
    """Of the board's variables, those a run outside the sandbox starts without.

    The same allowlist as inside it: no list of credential names can name every key, so a
    variable the run does not need is left out, whatever it is called.
    """
    return left_out(runtime, names)


def left_out(runtime: str, names: Iterable[str]) -> list[str]:
    """Of the board's variables, those a run starts without, in the sandbox or not.

    All but the base ones and, for claude, its keys and `CLAUDE_VARIABLES`.
    """
    claude = runtime == "claude"
    return [
        name
        for name in names
        if name not in BASE_VARIABLES
        and not (claude and (name in RUNTIME_VARIABLES or name in CLAUDE_VARIABLES))
    ]

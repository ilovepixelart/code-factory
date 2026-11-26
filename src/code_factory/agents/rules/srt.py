"""The settings of srt for each kind of work the board contains.

A kind differs by the hosts it reaches, what it may read inside the folders every sandbox is
denied, where it writes and what it may not write there. Every kind denies the state folder and
the secret files to read and every secret and connection key variable.
"""

import json
from collections.abc import Sequence
from typing import Any

from code_factory.agents.models.constants import SECRET_FILES
from code_factory.agents.rules.hooks import MCP_TOKEN_VARIABLE
from code_factory.agents.rules.settings import denied_variables


def _srt(  # noqa: PLR0913  # what one kind of sandbox differs by, named
    *,
    state: Sequence[str],
    hosts: Sequence[str],
    reads: Sequence[str],
    writes: Sequence[str],
    denied: Sequence[str],
    keys: Sequence[str],
    local_binding: bool = False,
    keep_mcp: bool = False,
) -> str:
    settings: dict[str, Any] = {
        "network": {
            "allowedDomains": list(hosts),
            "deniedDomains": [],
            "allowLocalBinding": local_binding,
        },
        "filesystem": {
            "denyRead": [*state, *SECRET_FILES],
            "allowRead": list(reads),
            "allowWrite": list(writes),
            "denyWrite": list(denied),
        },
        "credentials": {
            "envVars": [
                entry
                for entry in denied_variables(list(keys))
                if not keep_mcp or entry["name"] != MCP_TOKEN_VARIABLE
            ]
        },
    }
    return json.dumps(settings)


def process_settings(  # noqa: PLR0913  # what one kind of sandbox differs by, named
    *,
    state: Sequence[str],
    hosts: Sequence[str],
    writes: Sequence[str],
    denied: Sequence[str],
    reads: Sequence[str],
    keys: Sequence[str],
    keep_mcp: bool = False,
) -> str:
    """The settings of srt for a run whose whole process is inside, reaching `hosts` and no other.

    The reads of a claude run's sandbox but `reads` (folders inside those); writes to `writes`
    only (its worktree, its branch and the gate's lock folder), never to `denied`, what git reads
    later outside the sandbox.
    """
    return _srt(
        state=state, hosts=hosts, reads=reads, writes=writes, denied=denied, keys=keys,
        keep_mcp=keep_mcp,
    )  # fmt: skip


def _contained(  # noqa: PLR0913  # the places and the profile of one kind of work, named
    *,
    state: Sequence[str],
    home: str,
    tree: str,
    log: str,
    scratch: str,
    keys: Sequence[str],
    hosts: Sequence[str],
    denied: Sequence[str],
    local_binding: bool,
) -> str:
    # A command writing to its log reads its state, and `cat` and node fail on an output the
    # sandbox refuses; the log is in the denied state folder, and so may be the tree it runs in.
    reads = [log, *([tree] if tree == home or tree.startswith(f"{home.rstrip('/')}/") else [])]
    return _srt(
        state=state,
        hosts=hosts,
        reads=reads,
        writes=[tree, scratch],
        denied=denied,
        keys=keys,
        local_binding=local_binding,
    )


def tree_settings(  # noqa: PLR0913  # the places and the profile of one kind of work, named
    *,
    state: Sequence[str],
    home: str,
    tree: str,
    log: str,
    scratch: str,
    keys: Sequence[str],
    hosts: Sequence[str],
    denied: Sequence[str],
) -> str:
    """The settings of srt for a command the board runs on code a run wrote in `tree`.

    Its checks and the worktree hooks: no read of the state folder or the secret files but `log`
    (and `tree` when it is inside the state folder `home`), no port on this machine, writes only to
    `tree` but `denied`, and to `scratch`. Only the worktree setup, which installs packages, passes
    `hosts`; otherwise none.
    """
    return _contained(
        state=state, home=home, tree=tree, log=log, scratch=scratch, keys=keys,
        hosts=hosts, denied=denied, local_binding=False,
    )  # fmt: skip


def preview_settings(  # noqa: PLR0913  # the places and the profile of one kind of work, named
    *,
    state: Sequence[str],
    home: str,
    tree: str,
    log: str,
    scratch: str,
    keys: Sequence[str],
    denied: Sequence[str],
) -> str:
    """The settings of srt for a ticket's live preview.

    `tree_settings` with no host, and the ports of this machine to listen on, since the preview
    serves on one.

    srt's switch for that also lets the preview connect to any port on this machine, the board's
    own and its key broker's among them, which answer 403 and 401 without credentials; no other
    profile sets it.
    """
    return _contained(
        state=state, home=home, tree=tree, log=log, scratch=scratch, keys=keys,
        hosts=[], denied=denied, local_binding=True,
    )  # fmt: skip


def git_settings(  # noqa: PLR0913  # the places and the profile of one kind of work, named
    *,
    state: Sequence[str],
    home: str,
    tree: str,
    log: str,
    scratch: str,
    keys: Sequence[str],
    denied: Sequence[str],
) -> str:
    """The settings of srt for a git command the board runs that writes in the clone `tree`.

    `tree_settings` with no host; `denied` is what a run in the clone may not write
    (`kept_writes`), or the tree's `.git` whole for any other tree.
    """
    return _contained(
        state=state, home=home, tree=tree, log=log, scratch=scratch, keys=keys,
        hosts=[], denied=denied, local_binding=False,
    )  # fmt: skip

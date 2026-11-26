"""The rewrite a `git <subcommand> ...` command makes, read from its words.

Imports nothing: see `rewrite_guard`.
"""


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


LONG_PREFIX = 2  # `--am` is an option of git; `--a` is not enough to name one
# Words that start a command in a compound statement without being the program.
GIT_VALUED = _words("-c --git-dir --work-tree --namespace --super-prefix --config-env")
COMMIT_VALUED = _words(
    "--message --file --author --date --template --reuse-message --reedit-message --fixup --squash"
)
REBASE_VALUED = _words("-s -X -x -C --strategy --strategy-option --exec")
REBASE_ENDS = _words("--abort --continue --skip --quit --edit-todo --show-current-patch")
PUSH_VALUED = _words("-o --push-option --repo --receive-pack --exec")
BRANCH_VALUED = _words("-u --set-upstream-to --contains --no-contains --merged --no-merged")
UNSET = ("false", "no", "off", "0", "")


class Value:
    """Equality and `repr` by the slots, for the few small values this file returns."""

    __slots__ = ()

    def _fields(self) -> tuple[object, ...]:
        return tuple(getattr(self, name) for name in self.__slots__)

    def __eq__(self, other: object) -> bool:  # ty: ignore[missing-override-decorator]  # no import of typing
        """Equal when of one type and every slot is."""
        return type(other) is type(self) and self._fields() == other._fields()

    def __hash__(self) -> int:  # ty: ignore[missing-override-decorator]
        """Hashed by the slots."""
        return hash(self._fields())

    def __repr__(self) -> str:  # ty: ignore[missing-override-decorator]
        """The type and its slots."""
        return f"{type(self).__name__}{self._fields()!r}"


class Action(Value):
    """A way of rewriting history: `kind` and what it names (`value`).

    kinds: `amend`; `rebase` (value: the revision it replays onto, `None` for the upstream);
    `rebase_root`; `reset` (the revision); `force`; `pull_rebase`; `delete` (the branch names);
    `move` (the branch name, `HEAD` for the checked-out one).
    """

    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: str | tuple[str, ...] | None = None) -> None:
        self.kind = kind
        self.value = value


AMEND = Action("amend")
FORCE = Action("force")
PULL_REBASE = Action("pull_rebase")
REBASE_ROOT = Action("rebase_root")


def rebase(rev: str | None) -> Action:
    """A rebase onto `rev`; onto the upstream when `rev` is `None`."""
    return Action("rebase", rev)


def reset(rev: str) -> Action:
    """A reset to `rev`."""
    return Action("reset", rev)


def delete(names: tuple[str, ...]) -> Action:
    """Branches a push or `git branch` removes."""
    return Action("delete", names)


def move(name: str) -> Action:
    """The branch `git branch -f` or `git update-ref` points elsewhere."""
    return Action("move", name)


def git_action(sub: str, rest: list[str], *, config_rebases: bool) -> Action | None:
    """The rewrite of `git <sub> <rest>`, `None` for a command that rewrites nothing."""
    if sub == "pull":
        rebasing = _pulls_rebasing(rest) or (config_rebases and not _pull_unrebased(rest))
        return PULL_REBASE if rebasing else None
    handler = _SUBCOMMANDS.get(sub)
    return None if handler is None else handler(rest)


def _options(rest: list[str]) -> list[str]:
    """The words before a bare `--`."""
    return rest[: rest.index("--")] if "--" in rest else rest


def _takes_next(bundle: str, valued: str) -> bool:
    """Whether a short-option bundle (`-am`) ends in an option that takes the next word."""
    letters = bundle.lstrip("-")
    return any(c in valued for c in letters) and next(
        i for i, c in enumerate(letters) if c in valued
    ) + 1 == len(letters)


def _amends(rest: list[str]) -> bool:
    words = iter(_options(rest))
    for word in words:
        if word.startswith("--"):
            long = word[2:]
            # git accepts any unambiguous prefix of a long option; `--am` is only `--amend`.
            if _prefix_of(long, "amend"):
                return True
            if word in COMMIT_VALUED:
                next(words, None)
        elif word.startswith("-") and _takes_next(word, "mFCct"):
            next(words, None)
    return False


def _forces(rest: list[str]) -> bool:
    return any(
        word.startswith(("--force", "+"))
        or (word.startswith("-") and not word.startswith("--") and "f" in word)
        for word in _options(rest)
    )


def _prefix_of(word: str, full: str, shortest: int = LONG_PREFIX) -> bool:
    return len(word) >= shortest and full.startswith(word)


def _push(rest: list[str]) -> Action | None:
    if _forces(rest):
        return FORCE
    flags, plain = _partition(rest, PUSH_VALUED)
    deleting = any(
        _prefix_of(flag[2:], "delete") if flag.startswith("--") else "d" in flag for flag in flags
    )
    # The first plain word is the remote; the rest are refspecs.
    specs = plain[1:] if deleting else [s[1:] for s in plain[1:] if s.startswith(":")]
    names = tuple(name for spec in specs if (name := _branch_name(spec)))
    return delete(names) if names else None


def _pulls_rebasing(rest: list[str]) -> bool:
    """`--rebase` (any value but `false`), an unambiguous prefix of it, or `-r` in a bundle."""
    for word in _options(rest):
        if word.startswith("--"):
            name, _, value = word[2:].partition("=")
            if _prefix_of(name, "rebase", 3) and value != "false":
                return True
        elif word.startswith("-"):
            # `-s`, `-X` and `-S` take the rest of the bundle as their value.
            letters = word[1:]
            cut = min((letters.find(c) for c in "sXS" if c in letters), default=len(letters))
            if "r" in letters[:cut]:
                return True
    return False


def rebase_setting(setting: str, *, literal: bool) -> bool:
    """Whether a `name=value` given to git's own `-c` or `--config-env` makes `git pull` rebase.

    `pull.rebase` or `branch.<name>.rebase` with a value other than false. A `--config-env` value
    names an environment variable, so it cannot be read and counts as rebasing.
    """
    key, _, value = setting.partition("=") if "=" in setting else (setting, "", "true")
    key = key.lower()
    named = key == "pull.rebase" or (key.startswith("branch.") and key.endswith(".rebase"))
    return named and not (literal and value.lower() in UNSET)


def _pull_unrebased(rest: list[str]) -> bool:
    """Whether the pull's own options turn rebasing off, which wins over a `-c` setting."""
    return any(word in ("--no-rebase", "--rebase=false") for word in _options(rest))


def _branch(rest: list[str]) -> Action | None:
    flags, plain = _partition(rest, BRANCH_VALUED)

    def short(letters: str) -> bool:
        return any(not f.startswith("--") and any(c in letters for c in f[1:]) for f in flags)

    if short("mMcC") or "--move" in flags or "--copy" in flags:
        return None
    force = short("fD") or "--force" in flags
    removing = short("dD") or "--delete" in flags
    if removing and force:
        names = tuple(_branch_name(name) for name in plain)
        return delete(names) if names else None
    return move(_branch_name(plain[0])) if plain and force and not removing else None


def _update_ref(rest: list[str]) -> Action | None:
    """`git update-ref <ref>`: a branch ref, or `HEAD`, which is the checked-out branch."""
    flags, plain = _partition(rest, frozenset(("-m",)))
    # The refs a `--stdin` batch touches cannot be seen: it moves the checked-out branch.
    if any(flag in ("--stdin", "-z") for flag in flags):
        return move("HEAD")
    if not plain or not (plain[0] == "HEAD" or plain[0].startswith("refs/heads/")):
        return None
    return move(_branch_name(plain[0]))


def _branch_name(name: str) -> str:
    """The branch a ref or refspec destination names: `refs/` and `heads/` dropped."""
    return name.removeprefix("refs/").removeprefix("heads/")


def _partition(rest: list[str], valued: frozenset[str]) -> tuple[list[str], list[str]]:
    """The option words and the other words; a valued option takes the next word.

    Every word after a bare `--` is a plain one.
    """
    flags: list[str] = []
    plain: list[str] = []
    dashes = False
    words = iter(rest)
    for word in words:
        if dashes or not word.startswith("-"):
            plain.append(word)
        elif word == "--":
            dashes = True
        else:
            flags.append(word)
            if word in valued:
                next(words, None)
    return flags, plain


def _rebase(rest: list[str]) -> Action | None:
    onto = upstream = None
    root = False
    words = iter(rest)
    for word in words:
        if word in REBASE_ENDS:
            return None
        if word == "--onto":
            onto = next(words, None)
        elif word.startswith("--onto="):
            onto = word.removeprefix("--onto=")
        elif word == "--root":
            root = True
        elif word in REBASE_VALUED:
            next(words, None)
        elif not word.startswith("-") and upstream is None:
            upstream = word
    if root:
        return REBASE_ROOT
    return rebase(onto if onto is not None else upstream)


def _reset(rest: list[str]) -> str | None:
    """The commit a `git reset` moves to; `None` when it names none or only resets paths."""
    if any(word in ("--", "-p", "--patch") for word in rest):
        return None
    return next((word for word in rest if not word.startswith("-")), None)


def _commit(rest: list[str]) -> Action | None:
    return AMEND if _amends(rest) else None


def _reset_to(rest: list[str]) -> Action | None:
    rev = _reset(rest)
    return None if rev is None else reset(rev)


_SUBCOMMANDS = {
    "commit": _commit,
    "push": _push,
    "branch": _branch,
    "update-ref": _update_ref,
    "rebase": _rebase,
    "reset": _reset_to,
}

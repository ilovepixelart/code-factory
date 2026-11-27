"""Reading a shell command as a shell reads it: quotes, separators, wrappers, `cd` and `sh -c`.

Imports nothing: see `rewrite_guard`.
"""


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Words that start a command in a compound statement without being the program.
LEADING = _words("env command exec sudo nohup time then do else elif if while !")
SHELLS = _words("sh bash zsh dash ksh")


def shell_script(words: list[str]) -> str | None:
    """The script of `sh -c script` or `bash -lc script`."""
    for at, word in enumerate(words):
        if word.startswith("-") and not word.startswith("--") and "c" in word:
            return words[at + 1] if at + 1 < len(words) else None
    return None


def is_assignment(word: str) -> bool:
    """Whether the word is `NAME=value`."""
    name, equals, _ = word.partition("=")
    return bool(equals) and bool(name) and all(c.isalnum() or c == "_" for c in name)


def program_words(words: list[str]) -> list[str]:
    """The words from the program on: leading assignments, wrappers and their options dropped."""
    at = 0
    while at < len(words):
        word = words[at]
        wrapped = at > 0 and word.startswith("-") and words[0] in LEADING
        if not (is_assignment(word) or wrapped or word in LEADING):
            break
        at += 1
    return words[at:]


def resolve(directory: str, target: str) -> str:
    """The folder `cd target` reaches from `directory`; the parent of the root is the root."""
    absolute = directory.startswith("/") or target.startswith("/")
    parts = [] if target.startswith("/") else [p for p in directory.split("/") if p]
    for part in target.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return ("/" if absolute else "") + "/".join(parts)


class _Splitter:
    """The state of `segments`: the finished commands, the open one and the word being read."""

    def __init__(self) -> None:
        self.out: list[list[str]] = []
        self.words: list[str] = []
        self.word: str | None = None

    def end_word(self) -> None:
        if self.word is not None:
            self.words.append(self.word)
            self.word = None

    def end_command(self) -> None:
        self.end_word()
        if self.words:
            self.out.append(self.words)
            self.words = []

    def add(self, text: str) -> None:
        self.word = (self.word or "") + text

    def read(self, text: str, at: int) -> int:
        """Consume the character at `at` and anything it quotes; the index after them."""
        char = text[at]
        at += 1
        if char in " \t\r":
            self.end_word()
        elif char in "\n;&|()`":
            self.end_command()
        elif char == "'":
            stop = text.find("'", at)
            stop = len(text) if stop < 0 else stop
            self.add(text[at:stop])
            at = stop + 1
        elif char == '"':
            quoted, at = double_quoted(text, at)
            self.add(quoted)
        elif char == "\\":
            self.add(text[at : at + 1])
            at += 1
        else:
            self.add(char)
        return at


def segments(text: str) -> list[list[str]]:
    """The simple commands of a shell command, split at `; & | ( )`, backquotes and newlines."""
    splitter = _Splitter()
    at = 0
    while at < len(text):
        at = splitter.read(text, at)
    splitter.end_command()
    return splitter.out


def double_quoted(text: str, at: int) -> tuple[str, int]:
    r"""A double-quoted string's text and where it ends: a backslash escapes only `"` and `\`."""
    out: list[str] = []
    end = len(text)
    while at < end:
        char = text[at]
        at += 1
        if char == '"':
            break
        if char == "\\":
            if at >= end:
                break
            escaped = text[at]
            at += 1
            out.append(escaped if escaped in '"\\' else "\\" + escaped)
        else:
            out.append(char)
    return "".join(out), at

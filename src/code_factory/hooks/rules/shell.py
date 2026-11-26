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


def segments(text: str) -> list[list[str]]:
    """The simple commands of a shell command, split at `; & | ( )`, backquotes and newlines."""
    out: list[list[str]] = []
    words: list[str] = []
    word: str | None = None
    at, end = 0, len(text)
    while at < end:
        char = text[at]
        at += 1
        if char in " \t\r":
            if word is not None:
                words.append(word)
                word = None
        elif char in "\n;&|()`":
            if word is not None:
                words.append(word)
                word = None
            if words:
                out.append(words)
                words = []
        elif char == "'":
            stop = text.find("'", at)
            stop = end if stop < 0 else stop
            word = (word or "") + text[at:stop]
            at = stop + 1
        elif char == '"':
            quoted, at = double_quoted(text, at)
            word = (word or "") + quoted
        elif char == "\\":
            word = (word or "") + text[at : at + 1]
            at += 1
        else:
            word = (word or "") + char
    if word is not None:
        words.append(word)
    if words:
        out.append(words)
    return out


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

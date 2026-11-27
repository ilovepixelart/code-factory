"""A runtime's command line: its template filled with a run's words, split as a POSIX shell."""

from dataclasses import dataclass

from code_factory.platform.errors import BadRequestError

LOCAL_FLAGS = ("--tools", "Bash,Read,Edit,Write,Skill")
_QUOTE_OPEN = "No closing quotation"


@dataclass(frozen=True)
class CommandParts:
    """The values a command template's placeholders take.

    `remaining` is the spending cap in dollars, `settings` and `mcp` are the JSON strings of the
    flags of those names, `local` whether the run's model is served on this machine.
    """

    prompt: str
    permissions: str
    remaining: float | None
    settings: str | None
    model: str
    mcp: str
    local: bool


def _single(text: str, at: int) -> tuple[str, int]:
    end = text.find("'", at)
    if end < 0:
        raise BadRequestError(_QUOTE_OPEN)
    return text[at:end], end + 1


def _double(text: str, at: int) -> tuple[str, int]:
    out: list[str] = []
    while at < len(text):
        char = text[at]
        if char == '"':
            return "".join(out), at + 1
        if char == "\\":
            if at + 1 >= len(text):
                break
            following = text[at + 1]
            out.append(following if following in '"\\' else "\\" + following)
            at += 2
            continue
        out.append(char)
        at += 1
    raise BadRequestError(_QUOTE_OPEN)


def _piece(text: str, char: str, at: int) -> tuple[str, int]:
    """The text a non-blank `char` adds to its word, and where reading goes on at `at`."""
    if char == "'":
        return _single(text, at)
    if char == '"':
        return _double(text, at)
    if char != "\\":
        return char, at
    if at >= len(text):
        msg = "No escaped character"
        raise BadRequestError(msg)
    return text[at], at + 1


def shell_words(text: str) -> list[str]:
    r"""`text` split as a POSIX shell splits it.

    Whitespace apart, quotes keep words together, a backslash escapes any character outside
    quotes and only `"` or `\\` inside double quotes.
    """
    words: list[str] = []
    word: str | None = None
    at = 0
    while at < len(text):
        char = text[at]
        at += 1
        if char in " \t\n\r":
            if word is not None:
                words.append(word)
                word = None
        else:
            piece, at = _piece(text, char, at)
            word = (word or "") + piece
    if word is not None:
        words.append(word)
    return words


def _formatted(word: str, parts: CommandParts) -> str:
    """`str.format` with `prompt` and `permissions`: doubled braces are literal."""
    out: list[str] = []
    at = 0
    while at < len(word):
        char = word[at]
        if char in "{}" and word[at : at + 2] == char * 2:
            out.append(char)
            at += 2
        elif char == "{" and (end := word.find("}", at)) > 0:
            name = word[at + 1 : end]
            values = {"prompt": parts.prompt, "permissions": parts.permissions}
            if name not in values:
                msg = f"the agent command names an unknown {{{name}}}"
                raise BadRequestError(msg)
            out.append(values[name])
            at = end + 1
        elif char in "{}":
            msg = "the agent command has an unmatched brace"
            raise BadRequestError(msg)
        else:
            out.append(char)
            at += 1
    return "".join(out)


def _flag(word: str, parts: CommandParts) -> list[str] | None:
    """The words a placeholder word stands for; None when `word` is not one."""
    # Claude Code runs hooks and MCP servers outside its sandbox: no settings file loads but the
    # board's own (a run could write one into its worktree), and of the MCP servers only its own.
    flags: dict[str, list[str]] = {
        "{budget_flag}": []
        if parts.remaining is None
        else ["--max-budget-usd", f"{parts.remaining:.2f}"],
        "{settings_flag}": []
        if parts.settings is None
        else ["--settings", parts.settings, "--setting-sources="],
        "{mcp_flag}": ["--mcp-config", parts.mcp, "--strict-mcp-config"] if parts.mcp else [],
        "{model_flag}": ["--model", parts.model] if parts.model else [],
        "{local_flags}": list(LOCAL_FLAGS) if parts.local else [],
    }
    return flags.get(word)


def command_for(template: str, parts: CommandParts) -> list[str]:
    """The command template filled with a run's words, split as a POSIX shell splits it.

    A word is split first and filled after, so a prompt that looks like a placeholder or holds
    shell text stays one argument.
    """
    words: list[str] = []
    for word in shell_words(template):
        flag = _flag(word, parts)
        words.extend(flag if flag is not None else [_formatted(word, parts)])
    return words

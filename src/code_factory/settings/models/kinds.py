"""The kinds of value a `config.toml` key takes, each with its wording.

A kind validates strictly (TOML `true` is a bool, never the integer 1) and fails with the wording
itself, so the error text, the typed reader and the generated reference page all come from the
same field declaration. A key reads as `Count | None`: the default of a key belongs to the module
that acts on it.
"""

from typing import Annotated, Any, override

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, PydanticCustomError, core_schema

from code_factory.settings.models.predicates import (
    INTAKE_KEY_PREFIX,
    LINEAR_API,
    documents_entry,
    host_port,
    is_glob,
    is_prefix,
    key_name,
    tracker_allowed,
)

TICKET_TYPES = ("feature", "bug", "refactor", "upgrade", "hotfix", "docs")
PERIODS = ("day", "week", "month")
ERROR_TYPE = "setting"


def _int(value: object) -> int | None:
    """`value` when it is an integer, which a bool (TOML `true`) is not."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> int | float | None:
    """`value` when it is an integer or a float, which a bool is not."""
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _is_texts(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_text(value: object) -> bool:
    return isinstance(value, str)


def quoted(text: str) -> str:
    """`text` in double quotes with backslash and quote escaped, as the reports show a value."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Kind:
    """A kind of value: `words` says what it is, `problem` says why a value is not one."""

    words: str

    def accepts(self, value: object) -> bool:
        """Whether `value` is of this kind."""
        raise NotImplementedError

    def problem(self, value: object) -> str | None:
        """The sentence for a value of another kind, or None when it fits."""
        return None if self.accepts(value) else f"expected {self.words}"

    def read(self, value: object) -> Any:  # noqa: ANN401  # the value as written
        """The value as the model holds it."""
        return value

    def __get_pydantic_core_schema__(
        self, _source: object, _handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """Pydantic's hook: this kind validates, nothing else does."""
        return core_schema.no_info_plain_validator_function(self._validate)

    def _validate(self, value: object) -> Any:  # noqa: ANN401
        message = self.problem(value)
        if message is not None:
            raise PydanticCustomError(ERROR_TYPE, "{message}", {"message": message})
        return self.read(value)


class _Text(Kind):
    words = "text, not empty"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, str) and bool(value)


class _Count(Kind):
    words = "a positive integer"

    @override
    def accepts(self, value: object) -> bool:
        number = _int(value)
        return number is not None and number > 0


class _Whole(Kind):
    words = "a whole number, 0 or more"

    @override
    def accepts(self, value: object) -> bool:
        number = _int(value)
        return number is not None and number >= 0


class _Number(Kind):
    words = "a number"

    @override
    def accepts(self, value: object) -> bool:
        return _number(value) is not None


class _Flag(Kind):
    words = "true or false"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, bool)


class _Texts(Kind):
    words = "a list of text"

    @override
    def accepts(self, value: object) -> bool:
        return _is_texts(value)


class _Globs(Kind):
    words = "a list of text"

    @override
    def accepts(self, value: object) -> bool:
        return _is_texts(value)

    @override
    def problem(self, value: object) -> str | None:
        if isinstance(value, list):
            bad = next((p for p in value if isinstance(p, str) and not is_glob(p)), None)
            if bad is not None:
                return f"{quoted(bad)} is not a path pattern"
        return super().problem(value)


class _TextTable(Kind):
    words = "a table of text"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, dict) and all(isinstance(item, str) for item in value.values())


class _Prefix(Kind):
    words = "1 to 10 capital letters or digits, a letter first"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, str) and is_prefix(value)


class _TrackerKey(Kind):
    words = f"{INTAKE_KEY_PREFIX}, then capitals, digits or _"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, str) and key_name(value)


class _HostPorts(Kind):
    words = "a list of <host>:<port> texts"

    @override
    def accepts(self, value: object) -> bool:
        return isinstance(value, list) and all(
            isinstance(item, str) and host_port(item) for item in value
        )


class _Documents(Kind):
    words = "a list of requirements, spec and uat holding requirements, each once"

    @override
    def accepts(self, value: object) -> bool:
        return documents_entry(value) is not None

    @override
    def read(self, value: object) -> Any:
        return list(documents_entry(value) or ())


class OneOf(Kind):
    """One of a few words."""

    def __init__(self, *allowed: str) -> None:
        self.allowed = allowed
        self.words = f"one of {', '.join(allowed)}"

    @override
    def accepts(self, value: object) -> bool:
        """Whether `value` is of this kind."""
        return isinstance(value, str) and value in self.allowed


class TrackerAddress(Kind):
    """An issue tracker's address its key may go to: its own host, or this machine."""

    def __init__(self, tracker: str) -> None:
        self.tracker = tracker
        self.words = {
            "linear": f"{LINEAR_API} or an address on this machine",
            "slack": "https://slack.com/api or an address on this machine",
        }.get(tracker, "an https://<site>.atlassian.net address or one on this machine")

    @override
    def accepts(self, value: object) -> bool:
        """Whether `value` is of this kind."""
        return isinstance(value, str) and tracker_allowed(self.tracker, value)


class Between(Kind):
    """A whole number from `low` to `high`, both included."""

    def __init__(self, low: int, high: int) -> None:
        self.low, self.high = low, high
        self.words = f"a whole number from {low} to {high}"

    @override
    def accepts(self, value: object) -> bool:
        """Whether `value` is of this kind."""
        number = _int(value)
        return number is not None and self.low <= number <= self.high


class Share(Kind):
    """A number above 0 and at most `most`."""

    def __init__(self, most: float) -> None:
        self.most = most
        self.words = f"a number above 0 and at most {most}"

    @override
    def accepts(self, value: object) -> bool:
        """Whether `value` is of this kind."""
        number = _number(value)
        return number is not None and 0 < number <= self.most


Text = Annotated[str, _Text()]
Count = Annotated[int, _Count()]
Whole = Annotated[int, _Whole()]
Number = Annotated[int | float, _Number()]
Flag = Annotated[bool, _Flag()]
Texts = Annotated[list[str], _Texts()]
Globs = Annotated[list[str], _Globs()]
TextTable = Annotated[dict[str, str], _TextTable()]
Prefix = Annotated[str, _Prefix()]
TrackerKey = Annotated[str, _TrackerKey()]
HostPorts = Annotated[list[str], _HostPorts()]
Documents = Annotated[list[str], _Documents()]

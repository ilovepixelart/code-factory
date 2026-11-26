"""What a check of config.toml finds, before it has a line."""

from dataclasses import dataclass

LISTS = ("recurring", "automations", "scorers")


@dataclass(frozen=True)
class Finding:
    """One defect: the table (or list), the entry of a list, the key, and the sentence.

    `key` None means the table or the entry itself. `line_key` names the key whose line is
    reported when it is not `key`. A cross-key finding has `whole_entry` set for a list entry: the
    lenient reading drops the entry, not one key. `at_header` reports the line of the table's own
    header.
    """

    table: str
    index: int | None
    key: str | None
    message: str
    line_key: str | None = None
    whole_entry: bool = False
    at_header: bool = False

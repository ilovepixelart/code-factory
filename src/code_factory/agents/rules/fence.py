"""The owner's context in a prompt, and the redaction that keeps it and keys out of a log."""

import hashlib
import json
import re
import unicodedata

from code_factory.platform.errors import BadRequestError

PROMPT_LIMIT = 1_048_576
KEY_STAND_IN = "[redacted key]"
_MARKER = re.compile(r"owner\s+context", re.IGNORECASE)
_NONCE = re.compile(r"[A-Za-z0-9]{8,64}")
# The phrases the board's own fence lines are made of, each with the text that replaces it.
_PHRASES = (
    (re.compile(r"untrusted\s+ticket\s+data", re.IGNORECASE), "untrusted-ticket-data"),
    (re.compile(r"untrusted\s+notes", re.IGNORECASE), "untrusted-notes-text"),
)


def digest(text: str) -> str:
    """The first 12 hex characters of the SHA-256 of `text`."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def context_block(name: str, text: str, nonce: str) -> str:
    """What a run's prompt carries of the agent's context, fenced by the run's `nonce`.

    The run draws the nonce, so no text written before the block can close or forge the fence.
    """
    return (
        f"\n\nThe owner wrote the context below for the agent {name}, between the two lines "
        f"naming {nonce}. It is the owner's, not the ticket's: follow it where it does not "
        f"contradict the instructions above.\nBEGIN OWNER CONTEXT {nonce} FOR {name}\n{text}\n"
        f"END OWNER CONTEXT {nonce} FOR {name}"
    )


def checked_nonce(nonce: str) -> str:
    """`nonce` when it can name a fence: 8 to 64 letters or digits drawn for the run."""
    if _NONCE.fullmatch(nonce) is None:
        msg = "a fence needs a nonce of 8 to 64 letters or digits, drawn for the run"
        raise BadRequestError(msg)
    return nonce


def plain(text: str) -> str:
    """`text` as one compatibility form without format characters.

    Zero-width and joining characters (Unicode category Cf) are removed and full-width or styled
    letters become plain ones, so no spelling of a marker phrase hides from the match.
    """
    folded = unicodedata.normalize("NFKC", text)
    return "".join(char for char in folded if unicodedata.category(char) != "Cf")


def neutralised(text: str) -> str:
    """`text` in its `plain` form with the phrases of the board's fence lines neutralised.

    Any case and spacing. A fence line also names the run's nonce, so the neutralised text
    cannot forge one; the replacement keeps a marker from reading as a fence at all.
    """
    out = plain(text)
    for phrase, stand_in in _PHRASES:
        out = phrase.sub(stand_in, out)
    return out


def one_line(text: str) -> str:
    """`neutralised` text on one line: every control, separator and space run becomes one space."""
    spaced = "".join(
        " " if unicodedata.category(char)[0] in "CZ" else char for char in neutralised(text)
    )
    return " ".join(spaced.split())


def unmarked(text: str) -> str:
    """`text` with the fence's marker phrase neutralised, in any case and spacing.

    The board's text before the block (a note, a comment, a document) then cannot open or close a
    fence of its own.
    """
    return _MARKER.sub("owner-context-text", text)


def prompt_refusal(name: str, prompt: str) -> str | None:
    """Why a run of the agent cannot start with `prompt`: it is over 1,048,576 bytes."""
    size = len(prompt.encode())
    if size <= PROMPT_LIMIT:
        return None
    return (
        f"agent {name}: the prompt with its context is {size:,} bytes, past the "
        f"{PROMPT_LIMIT:,} a harness takes; shorten the agent's context"
    )


def placeholder(name: str, text: str) -> str:
    """What stands in a log for the agent's context of `text`."""
    return f"[owner context for {name}, {len(text):,} characters]"


def _forms(name: str, text: str) -> list[tuple[bytes, bytes]]:
    if not text:
        return []
    stand_in = placeholder(name, text).encode()
    forms = [(text.encode(), stand_in)]
    for ascii_only in (False, True):
        escaped = json.dumps(text, ensure_ascii=ascii_only)[1:-1]
        if escaped and escaped != text:
            forms.append((escaped.encode(), stand_in))
    return forms


class Redaction:
    """Every context, current and kept, as written and as a JSON string body, and every key.

    Never a text found between markers, which a payload could plant.
    """

    def __init__(self, patterns: list[tuple[bytes, bytes]]) -> None:
        # The longest first, so a context holding another is replaced whole.
        ordered = sorted(patterns, key=lambda pair: (-len(pair[0]), pair[0]))
        unique: dict[bytes, bytes] = {}
        for found, stand_in in ordered:
            unique.setdefault(found, stand_in)
        self._patterns = list(unique.items())

    @classmethod
    def of_contexts(
        cls, contexts: list[tuple[str, str]], keys: list[str] | None = None
    ) -> Redaction | None:
        """The redaction of `(agent name, text)` contexts and the key values a run was given."""
        patterns = [form for name, text in contexts for form in _forms(name, text)]
        patterns += [(key.encode(), KEY_STAND_IN.encode()) for key in keys or [] if key]
        return cls(patterns) if patterns else None

    def replaced(self, data: bytes) -> bytes:
        """`data` with every context and key replaced."""
        for found, stand_in in self._patterns:
            data = data.replace(found, stand_in)
        return data

    def spans(self, data: bytes) -> list[tuple[int, int, bytes]]:
        """Each `(start, end, stand-in)` of a match in `data`, in order, longest patterns first.

        An occurrence that overlaps a claimed one is not a match, as with `replaced`.
        """
        claimed: list[tuple[int, int, bytes]] = []
        for found, stand_in in self._patterns:
            at = data.find(found)
            while at >= 0:
                end = at + len(found)
                if all(end <= start or at >= stop for start, stop, _ in claimed):
                    claimed.append((at, end, stand_in))
                at = data.find(found, at + 1)
        return sorted(claimed)

    def apply(self, text: str) -> str:
        """`text` with every context and key replaced."""
        return self.replaced(text.encode()).decode(errors="replace")

    def stream(self) -> RedactedStream:
        """A redaction over a stream of output, chunk by chunk."""
        return RedactedStream(self)

    @property
    def longest(self) -> int:
        """The length of the longest pattern."""
        return max(len(found) for found, _ in self._patterns)


class RedactedStream:
    """A stream being redacted: it holds back the bytes that could start a pattern."""

    def __init__(self, redaction: Redaction) -> None:
        self._redaction = redaction
        self._held = b""

    def push(self, chunk: bytes) -> bytes:
        """What can be written of the stream once `chunk` arrived.

        A match is written only once it ends before the last `longest - 1` bytes: a pattern that
        can still start later starts there, so none can overlap a match written. A match that
        reaches into them is held whole, with everything after its start.
        """
        data = self._held + chunk
        safe = len(data) - (self._redaction.longest - 1)
        ready: list[bytes] = []
        at = 0
        cut = max(safe, 0)
        for start, end, stand_in in self._redaction.spans(data):
            if end > safe:
                cut = min(cut, start)
                break
            ready += [data[at:start], stand_in]
            at = end
        cut = max(at, cut)
        ready.append(data[at:cut])
        self._held = data[cut:]
        return b"".join(ready)

    def finish(self) -> bytes:
        """The rest of the stream, once it ended."""
        rest, self._held = self._held, b""
        return self._redaction.replaced(rest)

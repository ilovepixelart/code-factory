"""Values the sessions tests share: the golden files and the sample's clock."""

import json
import random
from pathlib import Path
from typing import Any

from code_factory.platform.text import render
from code_factory.sessions.models import Event, NewEvent
from code_factory.sessions.rules.events import event_row

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "sessions"
NOW = 1790001000.0


def golden(name: str) -> Any:  # noqa: ANN401  # parsed JSON of any shape
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def sample_files() -> dict[str, bytes]:
    """The sample's spool files: whole lines, a last line still being written, and bad lines."""
    sample = golden("sample.json")
    files: dict[str, bytes] = {
        name: "".join(render(payload) + "\n" for payload in payloads).encode()
        for name, payloads in sample["spool"].items()
    }
    for name, text in sample["raw"].items():
        files[name] = files.get(name, b"") + text.encode()
    return files


def sample_events() -> list[Event]:
    """The sample as the ledger holds it after one ingest: spools in name order, `seq` from 1."""
    found: list[Event] = []
    files = sample_files()
    for spool in sorted(files):
        offset = 0
        *whole, _partial = files[spool].split(b"\n")
        for line in whole:
            row = event_row(spool, offset, line)
            if isinstance(row, NewEvent):
                found.append(
                    Event(
                        len(found) + 1,
                        row.session_id,
                        row.agent_id,
                        row.event,
                        row.captured_at,
                        spool,
                        offset,
                        row.payload,
                    )
                )
            offset += len(line) + 1
    return found


def events_by_session(events: list[Event]) -> dict[str, list[Event]]:
    grouped: dict[str, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.session_id, []).append(event)
    return grouped


def answer(path: str) -> Any:  # noqa: ANN401  # parsed JSON of any shape
    return next(item for item in golden("answers.json") if item["path"] == path)


def noisy(seed: int, size: int) -> list[Event]:
    """Events with restarts, folders and transcripts coming and going."""
    rng = random.Random(seed)  # noqa: S311  # a reproducible test sequence
    names = ["PreToolUse"] * 4 + ["PostToolUse", "Stop", "UserPromptSubmit", "SessionStart"]
    names += ["SessionEnd", "PermissionRequest", "SubagentStart", "SubagentStop"]
    found = []
    for seq in range(1, size + 1):
        payload: dict[str, object] = {
            "tool_name": "Bash",
            "tool_use_id": rng.choice(["a", "b"]),
            "prompt": f"p{seq}",
        }
        if rng.random() < 0.3:
            payload["cwd"] = rng.choice(["/a", "/b", None])
        if rng.random() < 0.2:
            payload["transcript_path"] = rng.choice(["/t1", "/t2", None])
        found.append(
            Event(
                seq,
                "s",
                rng.choice([None, None, "x"]),
                rng.choice(names),
                float(seq),
                "s.jsonl",
                seq,
                payload,
            )
        )
    return found


def spool_lines(events: list[Event]) -> list[bytes]:
    """The hook payload lines of events, as the spool holds them."""
    lines = []
    for e in events:
        payload: dict[str, object] = {
            "session_id": e.session_id,
            "hook_event_name": e.event,
            **({"agent_id": e.agent_id} if e.agent_id is not None else {}),
            **e.payload,
            "_captured_at": e.captured_at,
        }
        lines.append(render(payload).encode() + b"\n")
    return lines

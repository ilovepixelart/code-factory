"""Scorers: who is asked, what an answer says, pass rates and when a scorer files a ticket."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from code_factory.evals.models import Answer, AnswerRow, Counts, Filed, Scorer, ScorerFiring
from code_factory.platform.text import masked

FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3
EVIDENCE_CUT = 300
DEFAULT_THRESHOLD = 10


def scorers_of(entries: Iterable[Mapping[str, object]]) -> list[Scorer]:
    """The configured scorers in file order; a repeated name keeps its first."""
    seen: set[str] = set()
    found: list[Scorer] = []
    for entry in entries:
        name = str(entry.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        threshold = entry.get("threshold")
        sample = entry.get("sample")
        found.append(
            Scorer(
                name=name,
                question=str(entry.get("question") or ""),
                stage=str(entry.get("stage") or ""),
                sample=float(sample) if isinstance(sample, int | float) else 1.0,
                threshold=max(1, int(threshold))
                if isinstance(threshold, int)
                else DEFAULT_THRESHOLD,
            )
        )
    return found


def _fnv(data: bytes) -> int:
    h = FNV_OFFSET
    for byte in data:
        h = ((h ^ byte) * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return h


def asked_of(scorer: Scorer, session: str, stage: str) -> bool:
    """Whether the scorer asks this session: its stage, then its sample share."""
    if scorer.stage and scorer.stage != stage:
        return False
    if scorer.sample >= 1:
        return True
    h = _fnv(scorer.name.encode() + b"\x00" + session.encode())
    return ((h >> 11) % 1_000_000) / 1_000_000 < scorer.sample


def parse_answer(text: str) -> tuple[Answer, str]:
    """(answer, evidence) from an agent's text; anything but yes or no is unclear."""
    answer, evidence = Answer.UNCLEAR, ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Answer:") and answer is Answer.UNCLEAR:
            words = stripped.removeprefix("Answer:").split()
            word = words[0].lower().rstrip(".!") if words else ""
            answer = Answer(word) if word in {"yes", "no"} else Answer.UNCLEAR
        elif stripped.startswith("Evidence:") and not evidence:
            evidence = masked(stripped.removeprefix("Evidence:").strip())[:EVIDENCE_CUT]
    return answer, evidence


def counts(rows: Iterable[AnswerRow], scorer: str, since: datetime) -> Counts:
    """Yes, no and unclear answers of the scorer at or after `since`."""
    tally = dict.fromkeys(Answer, 0)
    for row in rows:
        if row.scorer == scorer and row.at >= since:
            tally[row.answer] += 1
    return Counts(yes=tally[Answer.YES], no=tally[Answer.NO], unclear=tally[Answer.UNCLEAR])


def pass_rate(c: Counts) -> float | None:
    """Yes / (yes + no), `None` while nothing is decided."""
    decided = c.yes + c.no
    return c.yes / decided if decided else None


def _instant(source: str) -> int:
    try:
        return round(float(source.rsplit("@", 1)[1]) * 1_000_000)
    except IndexError, ValueError:
        return 0


def due(scorer: Scorer, rows: Sequence[AnswerRow], filed: Sequence[Filed]) -> ScorerFiring | None:
    """The ticket the scorer is due to file, or `None`."""
    prefix = f"scorer:{scorer.name}@"
    mine = [f for f in filed if f.source.startswith(prefix)]
    if any(f.open for f in mine):
        return None
    after = max((_instant(f.source) for f in mine), default=-1)
    failures: dict[str, AnswerRow] = {}
    for row in sorted(rows, key=lambda r: r.at):
        stamp = round(row.at.timestamp() * 1_000_000)
        if row.scorer == scorer.name and row.answer is Answer.NO and stamp > after:
            failures.setdefault(row.session_id, row)
    if len(failures) < scorer.threshold:
        return None
    newest = max(row.at for row in failures.values())
    return ScorerFiring(
        scorer=scorer.name,
        title=firing_title(scorer, len(failures)),
        body=firing_body(scorer, list(failures.values())),
        source=f"{prefix}{newest.timestamp():.6f}",
    )


def firing_title(scorer: Scorer, n: int) -> str:
    """The title of a scorer's ticket."""
    return f"Scorer {scorer.name}: {n} sessions answered no"


def firing_body(scorer: Scorer, failures: Sequence[AnswerRow]) -> str:
    """The question, then one line per failing session."""
    lines = [f"> {scorer.question}", ""]
    lines += [f"- {row.session_id}: {' '.join(row.evidence.split())}" for row in failures]
    return "\n".join(lines) + "\n"

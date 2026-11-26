"""Pure review rules: rule names, a review's shape, and where each finding stands."""

import re
from collections.abc import Iterable
from typing import Any, Literal

from code_factory.platform.errors import BadRequestError
from code_factory.tickets.models import Finding, FindingState, Problem, Review

_RULE = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
_RULE_TAG = re.compile(r"\s*\[rule:\s*([^\]]*?)\s*\]\s*$")
RULE_LIMIT = 40
BLOCKING = ("blocker", "major")


def plain_rule(name: str) -> bool:
    """Whether `name` is a plain rule name.

    Lower-case words of ASCII letters and digits joined by single hyphens, a letter first, at most
    40 characters. A name comes from an agent's output: it is compared and shown, never used as a
    path or a command.
    """
    return len(name) <= RULE_LIMIT and _RULE.fullmatch(name) is not None


def split_rule(text: str) -> tuple[str, str | None]:
    """A review item's text without its trailing `[rule: name]` tag, and the name it holds.

    The text whole and no name when it has no tag or the tag's name is not a plain rule name.
    """
    tag = _RULE_TAG.search(text)
    if tag is None or not plain_rule(tag.group(1)):
        return text, None
    name = str(tag.group(1))
    return text[: tag.start()], name


def rule_problems(review: str) -> list[Problem]:
    """The list items of a review whose trailing `[rule: ...]` tag holds no plain name."""
    problems = []
    for number, line in enumerate(review.splitlines(), start=1):
        item = line.lstrip()
        tag = _RULE_TAG.search(line) if item.startswith(("- ", "* ")) else None
        if tag is not None and not plain_rule(tag.group(1)):
            message = (
                f'rule: "{tag.group(1)}" is not a plain name '
                f"(lower-case words joined by hyphens, at most {RULE_LIMIT} characters)"
            )
            problems.append(Problem(line=number, message=message))
    return problems


def _check_finding(text: str, rule: str) -> None:
    if not text.strip():
        raise BadRequestError("a finding needs text: say what is missing, untested or wrong")
    if rule and not plain_rule(rule):
        msg = (
            f"{rule!r} is not a rule name: lower-case letters and digits joined by -, at most "
            f"{RULE_LIMIT} characters"
        )
        raise BadRequestError(msg)


def check_review(review: Review) -> None:
    """`BadRequestError` when the verdict and the findings disagree or a finding is malformed.

    `changes` needs at least one finding and `pass` has none.
    """
    if review.verdict == "changes" and not review.findings:
        raise BadRequestError("a changes verdict needs at least one finding")
    if review.verdict == "pass" and review.findings:
        raise BadRequestError("a pass verdict has no findings: submit changes, or drop them")
    for finding in review.findings:
        _check_finding(finding.text, finding.rule)


def finding_class(severity: str) -> Literal["important", "nit"]:
    """`important` for a blocker or a major finding, `nit` for the rest."""
    return "important" if severity in BLOCKING else "nit"


def _finding_line(finding: Finding, finding_id: str) -> str:
    place = finding.requirement_id or (
        f"{finding.path}:{finding.line}" if finding.line else finding.path
    )
    where = f" {place}:" if place else ""
    rule = f" [rule: {finding.rule}]" if finding.rule else ""
    return f"- {finding_id} [{finding.severity}]{where} {finding.text.strip()}{rule}"


def render_review(review: Review, ids: list[str]) -> str:
    """The review document: the verdict line, the summary, then one line per finding."""
    text = f"# Review\n\nVerdict: {review.verdict}\n\n{review.summary.strip()}\n"
    if review.findings:
        lines = [_finding_line(f, i) for f, i in zip(review.findings, ids, strict=True)]
        text += "\n## Findings\n\n" + "\n".join(lines) + "\n"
    return text


REASON_LIMIT = 1000


def check_reason(reason: str) -> str:
    """A dismissal's reason, stripped; `BadRequestError` when it is empty or too long."""
    text = reason.strip()
    if not text or len(text) > REASON_LIMIT:
        msg = (
            f"a dismissal needs a reason of 1 to {REASON_LIMIT} characters: "
            "say why the finding does not apply"
        )
        raise BadRequestError(msg)
    return text


FINDING_KINDS = (
    "finding",
    "finding.kept",
    "finding.dismissed",
    "finding.closed",
    "review_submitted",
)
FIXED_BY_LATER_REVIEW = "the review no longer raises it"
Trail = Iterable[tuple[str, str, dict[str, Any]]]


def _opened(data: dict[str, Any]) -> FindingState:
    return FindingState(
        id=data["id"],
        severity=data["severity"],
        finding_class=finding_class(data["severity"]),
        file=data.get("file", ""),
        line=data.get("line", 0),
        text=data.get("text", ""),
        rule=data.get("rule", ""),
        requirement=data.get("requirement", ""),
        state="open",
        reason="",
        by="",
    )


def findings_of(trail: Trail) -> tuple[list[FindingState], dict[int, list[str]]]:
    """Every finding of a ticket as its records leave it, and the findings each review listed.

    `trail` is the ticket's finding records `(kind, by, data)` in the order written. A finding is
    open when raised and when a review keeps it (which reopens a closed one); `finding.dismissed`
    and `finding.closed` close it with a reason and who closed it. The ids a review raised or kept
    belong to the version its `review_submitted` record names. The findings come in the order
    they were opened.
    """
    found: dict[str, FindingState] = {}
    listed: dict[int, list[str]] = {}
    pending: list[str] = []
    for kind, by, data in trail:
        if kind == "finding":
            found[data["id"]] = _opened(data)
            pending.append(data["id"])
        elif kind == "finding.kept" and data["id"] in found:
            update: dict[str, Any] = {"state": "open", "reason": "", "by": ""}
            if "severity" in data:
                update["severity"] = data["severity"]
                update["finding_class"] = finding_class(data["severity"])
            found[data["id"]] = found[data["id"]].model_copy(update=update)
            pending.append(data["id"])
        elif kind in ("finding.dismissed", "finding.closed") and data["id"] in found:
            state = "dismissed" if kind == "finding.dismissed" else data["state"]
            update = {"state": state, "reason": data["reason"], "by": by}
            found[data["id"]] = found[data["id"]].model_copy(update=update)
        elif kind == "review_submitted":
            listed[data["version"]] = pending
            pending = []
    return list(found.values()), listed


def listing_order(findings: list[FindingState]) -> list[FindingState]:
    """Blocking findings first, then nits, each group in the order opened."""
    return sorted(findings, key=lambda f: f.finding_class != "important")


def blocking(findings: list[FindingState]) -> list[FindingState]:
    """The open findings that send a review back."""
    return [f for f in findings if f.state == "open" and f.finding_class == "important"]

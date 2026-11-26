"""The task of each stage of a run: built in, replaced by the repository's own, filled and ended.

A task names the board's MCP tools (`write_document`, `post_note`, `dismiss_finding`); a test
compares every tool it names with the tool list a run is given. Documents are written with
`write_document`, never as files.
"""

from code_factory.agents.rules.fence import one_line
from code_factory.agents.rules.harness import IDENTIFIER

STAGES = ("spec", "build", "review", "critique", "read", "qa", "security", "tests")

_LIMITS = (
    " Commit after each green test. Test only what the change reaches, once. A test that fails "
    "then passes on one rerun is named in the report and left, with no stress runs. After a fix "
    "fails twice, stop and report rather than loop. Report in at most 8 lines."
)

_SPEC = (
    "Write the ticket's documents in this order, each with `write_document`: `requirements`, "
    "the problem and a Requirements table with one row per requirement ({id}-R1, {id}-R2, ...), "
    "each naming the test that checks it (the `write-requirements` skill). Plan new test files "
    "that match {tests}, or {e2e} for end-to-end tests. If a requested path conflicts with the "
    "applicable pattern, use `ask_question` to resolve it before finalizing the spec. For a ticket "
    "labelled ui, write the `mock`, marking each part with the requirement it shows (the "
    "`make-mock` skill); "
    "`spec`, the technical design and its decisions (the `write-spec` skill), ending with a "
    "`## Blast radius` section naming the modules, files, public interfaces and stored data the "
    "change touches and what could break, which Build waits for; and `uat`, the "
    "acceptance cases (the `write-uat` skill), which a refactor, an upgrade or a docs change "
    "leaves out." + _LIMITS
)

_BUILD = (
    "Develop the ticket, tests first: write the tests the spec names, as files matching the "
    "pattern {tests} and watch them fail; then implement the smallest code that makes them pass. "
    "Continue until the tests and the project's checks pass. Never remove or loosen an existing "
    "test to make it pass; when a requirement and an existing test conflict, ask the owner with "
    "`ask_question` instead. Follow the `build-ticket` skill, which builds the code with the `tdd`"
    " skill. A review finding you do not agree with is answered with `dismiss_finding` and a "
    "reason; one you agree with is fixed in code. Before your last commit, review your own diff "
    "against the ticket's requirements and the `review` skill's checklist, then fix and commit "
    "what you find. Last, append to the `notes` document a `## Behaviour` section: a table of what"
    " behaves differently, before and after, each row naming the test that shows it, then, where "
    "the project measures coverage, the coverage of the changed files before and after; it opens "
    "the pull request's description. Do not push." + _LIMITS
)

_REVIEW = (
    "Review the work on this ticket's branch against its requirements: read the diff of the "
    "branch against the default branch and the ticket's `spec` with `read_document`. Write the "
    "`review` document with `write_document`, one finding per requirement that is missing, "
    "untested or wrong, each a list item starting with its severity, [blocker], [major], [minor] "
    "or [nit], and citing a requirement id or path:line, and optionally ending with [rule: "
    "name], a short stable name for the rule it breaks (lower-case words joined by hyphens, at "
    "most 40 characters). A blocker or major finding citing only files the branch did not "
    "change, and no requirement id, is recorded as pre-existing and does not hold Review, so "
    "cite a defect the change causes in an unchanged file at the changed line that causes it. "
    "The ticket's activity lists the earlier findings with their ids and states: for one still "
    "open that the change has not fixed, start its item with its severity and id, as "
    "'- [major] F2: ...', its prior id; raise a fixed or dismissed one again only when the "
    "change brings it back. Findings the owner dismissed on other tickets are context, checked "
    "against the current diff: still raise a finding when this change shows the problem; they "
    "never lower the severity of, or suppress, a security finding. Change no other file. Follow "
    "the `review` skill." + _LIMITS
)

_CRITIQUE = (
    "Read this ticket's plan as one who did not write it: the ticket from `get_ticket` and its "
    "`notes` document from `read_document`, and nothing else. Look for a step that is missing, "
    "out of order or too large to check, a step no test could show done, and a part of the "
    "ticket's requirements that the plan leaves uncovered. Ask each objection with "
    "`ask_question`, naming the plan item, with two to four choices, each a short label with a "
    "description, the one you recommend marked. Write nothing when the plan holds. Change no "
    "other file."
)

_READ = (
    "Read this ticket's documents as one who did not write them: `requirements`, `spec` and "
    "`uat`, and the `mock` when there is one, each with `read_document`. Look for where they "
    "contradict each other, a requirement no test could hold, and a requirement no acceptance "
    "case covers. Ask each with `ask_question` about that document, naming its line, with two "
    "to four choices, each a short label with a description, the one you recommend marked. "
    "Write nothing when they agree. Change no other file."
)

# The roles a repository adds before its review (`[agents] review_roles`): each runs as its own
# agent with read-only tools, works its checklist and records findings tagged with its rule name.
REVIEW_ROLES = {
    "qa": (
        "As QA, try to break the change: for every acceptance case in `uat` and every "
        "requirement, run the flow the change reaches (its tests, the command or the page), "
        "then the edges the author did not test: empty, one, the largest, a repeat, a failure "
        "of what it calls. Call `get_qa_holdout` and run each private acceptance case as "
        "specified. For private cases, cite the case identifier and observable failure in a "
        "finding while keeping its private steps and inputs in the QA session. Raise each "
        "public-case break as a finding ending [rule: qa-break], with the input that broke it."
    ),
    "security": (
        "As a security auditor, read the diff for input reaching a query, a shell, a path or a "
        "page unescaped; a secret in code, a log or an error; a check of who may act that is "
        "missing or bypassable; and a dependency added without need. Raise each as a finding "
        "ending [rule: security-<kind>], with the line and how it is reached."
    ),
    "tests": (
        "As a test reviewer, check every requirement's named test exists, asserts the "
        "behaviour rather than that code ran, and would fail without the change: name a "
        "requirement whose test is missing, hollow or passes on the old code as a finding "
        "ending [rule: tests-hollow]."
    ),
}


_ROLE_RECORD = (
    " Read the ticket with `get_ticket`, its `requirements`, `spec` and `uat` with "
    "`read_document`, its activity, which holds the board's checks, with `list_activity`, and "
    "the branch's diff against the default branch. Record each finding with "
    "`post_note`, one per note, starting with its severity, [blocker], [major], [minor] or "
    "[nit], and citing a requirement id or path:line. Change no file; write nothing when you "
    "find nothing. The review that follows carries your findings."
)


def role_notes(roles: list[str]) -> str:
    """What a review is told of the roles that ran before it; empty when none of them is a role.

    Each role is a run of its own before the review (its task in `_TASKS`), whose findings are
    notes in the ticket's activity.
    """
    known = [role for role in roles if role in REVIEW_ROLES]
    if not known:
        return ""
    return (
        f"Before this review, the {', '.join(known)} review ran as runs of their own and "
        "recorded their findings as notes in the ticket's activity. Read them with "
        "`list_activity`: carry each that still holds on this diff into the `review` document as "
        "a finding of yours with its severity, rule and note_id from the activity; leave out one "
        "the diff disproves."
    )


def guardrail_note(sensitive_paths: list[str], large_change: int | None) -> str:
    """The repository's guardrails for a review: crossing one the ticket did not ask for returns it.

    Empty when the repository sets none.
    """
    rails = []
    if sensitive_paths:
        rails.append(f"a change to a path matching {', '.join(sensitive_paths)}")
    if large_change is not None:
        rails.append(f"more than {large_change} changed lines")
    if not rails:
        return ""
    return (
        f"The repository's guardrails: {'; '.join(rails)}. When the diff crosses one and the "
        "ticket's requirements do not ask for it, raise a [blocker] finding ending "
        "[rule: guardrail], which sends the change back to Build."
    )


_TASKS = {
    **{role: checklist + _ROLE_RECORD for role, checklist in REVIEW_ROLES.items()},
    "spec": _SPEC,
    "build": _BUILD,
    "review": _REVIEW,
    "critique": _CRITIQUE,
    "read": _READ,
}

# Where the board ships, the run's sandbox reaches no network host: the board pushes the branch.
BOARD_SHIPS = (
    "Do not push or open a pull request: once this run's work is done, the board pushes the "
    "branch and opens its pull request, and this run's part ends there."
)


def built_in_task(stage: str) -> str:
    """The stage's built-in task; build's for a stage that has none."""
    return _TASKS.get(stage, _BUILD)


def stage_instructions(own: str, stage: str) -> str:
    """A stage's task before its placeholders are filled: the repository's `own`, else built in."""
    return own.strip() or built_in_task(stage)


def _plain(pattern: str) -> str:
    return pattern if IDENTIFIER.fullmatch(pattern) else ""


def fill_task(task: str, ticket_id: str, tests: str, e2e: str) -> str:
    """`task` with `{id}`, `{e2e}` and `{tests}` replaced, once and by name.

    An empty pattern is `tests/e2e/*` or `tests/*`. Any other brace is kept, since a repository's
    own task may hold any, and a value that holds a placeholder is not expanded again. The task is
    the run's instruction, outside every fence, so a pattern that is not a plain one (the
    harness's `IDENTIFIER`) counts as empty, and the id is put on one line.
    """
    values = {
        "{id}": one_line(ticket_id),
        "{e2e}": _plain(e2e) or "tests/e2e/*",
        "{tests}": _plain(tests) or "tests/*",
    }
    out: list[str] = []
    at = 0
    while at < len(task):
        found = next((key for key in values if task.startswith(key, at)), None)
        out.append(task[at] if found is None else values[found])
        at += 1 if found is None else len(found)
    return "".join(out)


def plan_first(ticket_id: str, label: str) -> str:
    """What a build task ends with for a ticket labelled `label` that has no plan yet."""
    return (
        f"This ticket {ticket_id} is labelled {label}: before any code, write the plan as a "
        "markdown checklist in the `notes` document with `write_document`, one line `- [ ] item` "
        "for each step, and tick an item (`- [x]`) in the commit that finishes it."
    )


def rules_in_use_note(names: list[str]) -> str:
    """The sentence naming the finding rules already in use, most used first; empty for none."""
    if not names:
        return ""
    return (
        "Rule names already in use, most used first (end a finding's item with [rule: name], "
        f"reusing one of these when it is the same rule): {', '.join(names)}"
    )


def review_guide_note(base: str, guide: str) -> str:
    """The repository's review guide, as read from the commit `base`, for a review's task."""
    return (
        f"The repository's review guide (on {base}): what matters in review here. "
        f"Apply it:\n{guide}"
    )


def stage_task(  # noqa: PLR0913  # the suffixes one stage's task may take, named
    task: str,
    stage: str,
    *,
    plan: str = "",
    ships: bool = False,
    rules: str = "",
    guide: str = "",
    roles: str = "",
) -> str:
    """The filled `task` with what its stage adds, each only when there is one.

    A build gets its plan-first and ship sentences, a review its rules in use and review guide.
    """
    if stage == "build":
        extras = [plan, BOARD_SHIPS if ships else ""]
    elif stage == "review":
        extras = [rules, guide, roles]
    else:
        extras = []
    return "\n\n".join([task, *(extra for extra in extras if extra)])

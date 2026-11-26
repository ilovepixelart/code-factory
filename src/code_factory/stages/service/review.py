"""Reviews: what an ended review run decides, what holds a merge for one, the pins, the screens."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from code_factory.platform.errors import ConflictError, NotFoundError
from code_factory.stages import rules
from code_factory.stages.adapters import GitDiffReader, TestFiles
from code_factory.stages.models import BlockingFinding, Hold, Record, ReviewOutcome, ReviewVerdict
from code_factory.stages.repository import StageRepository
from code_factory.stages.service.assess import Assessing, acted_on
from code_factory.stages.service.base import ACTOR
from code_factory.tickets.models import DocumentName, Ticket

UNREADABLE_CHANGE = "Sensitive change: its settings or its diff cannot be read"


class Reviewing(Assessing):
    """The review decisions of the board and the holds a review puts on a merge."""

    async def apply_review(
        self, ticket: str, run_id: str, reviewed_head: str, now: datetime | None = None
    ) -> ReviewOutcome:
        """Decide what an ended review run does to the ticket.

        `pass` records a `passed` verdict on the head; `changes` records `returned` and sends the
        ticket back to Build; `halt` (the review returned it `[agents] review_rounds` times)
        records nothing and carries the sentence that tells the owner it decides. Only a review
        the run itself submitted counts (`ConflictError` otherwise), and applying the same run
        and head again answers what the first time did and writes nothing.
        """
        found = await self._ports.tickets.get(ticket)
        review = await self._ports.reviews.latest_review(ticket)
        blocking = await self._ports.reviews.blocking_findings(ticket)
        cap = (await self._agents(found.repository)).review_rounds
        before = acted_on(await self.assess(ticket)).stage
        at = now or self._clock()
        async with self._uow() as session:
            store = StageRepository(session)
            await store.lock(found.number)
            verdicts = await store.verdicts_of(found.number)
            returned = sum(v.outcome == "returned" for v in verdicts)
            replay = _replay(verdicts, run_id, reviewed_head)
            if replay is not None:
                return replay
            if review is None or review.by not in {run_id, f"run:{run_id}"}:
                raise ConflictError(
                    f"{found.id} has no review submitted by run {run_id}: submit one"
                )
            decision = rules.review_outcome(
                review.verdict, blocking_open=bool(blocking), returned=returned, cap=cap
            )
            if decision != "halt":
                outcome = "passed" if decision == "pass" else "returned"
                await store.add_verdict(
                    found.number, outcome, head=reviewed_head, run_id=run_id, why=("", ""), now=at
                )
            if decision == "changes":
                await store.set_declared(found.number, "build", ACTOR, at)
        if decision == "changes" and before != "build":
            moved: dict[str, object] = {"from": before, "to": "build"}
            await self._ports.tickets.record_activity(found.id, "stage", moved, by=ACTOR)
        sentence = ""
        if decision == "halt":
            sentence = (
                f"the review returned it {returned} times ([agents] review_rounds = {cap}): "
                "the owner decides whether it goes round again"
            )
        return ReviewOutcome(
            decision=decision, returned=returned + (decision == "changes"), sentence=sentence
        )

    async def review_fix_due(self, ticket: str) -> bool:
        """Whether a review returned this ticket to Build."""
        verdicts = await self.review_verdicts(ticket)
        latest = next((v for v in reversed(verdicts) if v.outcome != "skipped"), None)
        return (
            latest is not None
            and latest.outcome == "returned"
            and (await self.assess(ticket)).declared == "build"
        )

    async def fix_committed(self, ticket: str) -> None:
        """A ticket returned to Build by review follows its evidence after a fix commits."""
        if not await self.review_fix_due(ticket):
            return
        try:
            await self.declare(ticket, "", ACTOR, expect="build")
        except ConflictError:
            return

    async def record_review_skipped(self, ticket: str, head: str, reason: str, note: str) -> None:
        """Record that the review of `head` was skipped; `note` carries why, as a sentence."""
        number = await self._number(ticket)
        async with self._uow() as session:
            await StageRepository(session).add_verdict(
                number, "skipped", head=head, run_id="", why=(reason, note), now=self._clock()
            )

    async def review_verdicts(self, ticket: str) -> list[ReviewVerdict]:
        """The ticket's review decisions, oldest first."""
        number = await self._number(ticket)
        async with self._uow() as session:
            return await StageRepository(session).verdicts_of(number)

    async def _unreviewed(
        self, diff: GitDiffReader, head: str, limit: int, sensitive: Sequence[str]
    ) -> bool:
        """Whether the head merges without a review: plain files within the bound off the paths."""
        base = await diff.fork_point(head)
        if base is None:
            return False
        raw = await diff.diff(base, head, "--raw")
        stat = await diff.diff(base, head, "--numstat")
        if raw is None or stat is None:
            return False
        return rules.plain(raw) and rules.small(rules.numstat(stat), limit, sensitive)

    async def review_hold(  # the facts only the caller has
        self,
        ticket: str,
        head: str,
        ended_review_heads: Sequence[str],
        *,
        review_active: bool,
        now: datetime | None = None,
    ) -> Hold | None:
        """Why the board does not merge the ticket's ready pull request at `head` on its own.

        `ended_review_heads` are the heads of the review runs of the ticket that ended;
        `review_active` says a review run is running. An unreadable diff holds.
        """
        found = await self._ports.tickets.get(ticket)
        agents = await self._agents(found.repository)
        if agents.unreadable:
            return Hold(reason=UNREADABLE_CHANGE, owner=True)
        if not agents.review:
            return None
        diff = GitDiffReader(await self._root(found.repository), self._git)
        if agents.unreviewed_lines is not None and await self._unreviewed(
            diff, head, agents.unreviewed_lines, agents.sensitive
        ):
            return None
        return await self._hold_of(found, diff, head, (ended_review_heads, review_active), now)

    async def _hold_of(
        self,
        found: Ticket,
        diff: GitDiffReader,
        head: str,
        runs: tuple[Sequence[str], bool],
        now: datetime | None,
    ) -> Hold | None:
        ended_heads, active = runs
        async with self._uow() as session:
            verdicts = await StageRepository(session).verdicts_of(found.number)
        latest = next((v for v in reversed(verdicts) if v.outcome != "skipped"), None)
        passed = (
            latest is not None
            and latest.outcome == "passed"
            and await diff.same_code(latest.head, head)
        )
        ended = any([await diff.same_code(done, head) for done in ended_heads])
        skipped = next(
            (v for v in reversed(verdicts) if v.outcome == "skipped" and v.head == head), None
        )
        open_findings = await self._ports.reviews.blocking_findings(found.id)
        blocking = [
            BlockingFinding(id=f.id, severity=f.severity, text=f.text) for f in open_findings
        ]
        agents = await self._agents(found.repository)
        return rules.review_hold_decision(
            review_on=True,
            small=False,
            passed=passed,
            blocking=blocking,
            ended=ended,
            skipped_note=None if skipped is None else skipped.note,
            ready_since=_ready_since(await self._records(found.id), head),
            run_timeout=agents.run_timeout,
            review_active=active,
            now=now or self._clock(),
            head=head,
        )

    async def change_hold(self, ticket: str, head: str) -> str | None:
        """Why the head is the owner's to merge under `[agents] sensitive_paths` and `large_change`.

        A diff git cannot read holds: a rule that cannot be checked is not passed.
        """
        found = await self._ports.tickets.get(ticket)
        agents = await self._agents(found.repository)
        if agents.unreadable:
            return UNREADABLE_CHANGE
        if agents.large_change is None and not agents.sensitive_paths:
            return None
        diff = GitDiffReader(await self._root(found.repository), self._git)
        base = await diff.fork_point(head)
        raw = None if base is None else await diff.diff(base, head, "--raw")
        stat = None if base is None else await diff.diff(base, head, "--numstat")
        if raw is None or stat is None:
            return UNREADABLE_CHANGE
        reason = rules.change_hold(rules.numstat(stat), agents.large_change, agents.sensitive_paths)
        if reason is None and agents.large_change is not None and not rules.plain(raw):
            return (
                "Large change: its size cannot be counted, "
                f"against large_change {agents.large_change}"
            )
        return reason

    async def test_gaps(self, ticket: str, worktree: Path) -> list[str]:
        """What the ticket's tests name that nothing in the worktree defines.

        `no file matches <pattern>` for each `tests` and `e2e` pattern matching no file, then the
        requirements' named checks that no test file defines.
        """
        found = await self._ports.tickets.get(ticket)
        patterns = [*rules.patterns(found.tests), *rules.patterns(found.e2e)]
        sources = await TestFiles(worktree).read(patterns)
        defined = {
            name
            for path, text in sources.files.items()
            for pair in rules.check_nodes(path, text)
            for name in pair
        }
        missing = [f"no file matches {pattern}" for pattern in sources.unmatched]
        try:
            document = await self._ports.documents.get_document(found.id, DocumentName.REQUIREMENTS)
            requirements = rules.named_checks(document.body)
        except NotFoundError:
            requirements = []
        return [*missing, *rules.unresolved_checks(requirements, defined)]

    async def capture_state(self, ticket: str, tree: str) -> Record | None:
        """The capture the owner's approval waits on: it shows `tree` and is neither answered."""
        return rules.waiting_capture(await self._records(ticket), tree)

    async def answers_waiting(self, ticket: str) -> list[Record]:
        """The owner's answers recorded to be applied that no run has applied."""
        return rules.answers_waiting(await self._records(ticket))


def _replay(verdicts: Sequence[ReviewVerdict], run_id: str, head: str) -> ReviewOutcome | None:
    """What applying the run on the head answered the first time, from the verdicts before it."""
    for index, verdict in enumerate(verdicts):
        if verdict.run_id == run_id and verdict.head == head and verdict.outcome != "skipped":
            before = sum(v.outcome == "returned" for v in verdicts[:index])
            changes = verdict.outcome == "returned"
            return ReviewOutcome(
                decision="changes" if changes else "pass", returned=before + changes
            )
    return None


def _ready_since(records: Sequence[Record], head: str) -> datetime | None:
    """When the head became ready: the latest of its checks and of the board shipping it."""
    named = [
        r
        for r in records
        if (r.kind == "checks" and r.text("commit") == head and r.text("scope") != "fast")
        or (r.kind in {"pull_request", "branch_pushed"} and r.text("head") == head)
    ]
    return named[-1].at if named else None

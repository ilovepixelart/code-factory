"""The checks every entry meets on its way in, registered on the memory service."""

from code_factory.memory.models import Admission, Intake, NewMemory
from code_factory.memory_extras.models import DuplicateQuestion, TicketContext
from code_factory.memory_extras.rules import (
    alike,
    check_fields,
    draft_entry,
    duplicate_questions,
    everywhere,
    over_budget,
    paired_with,
    plan_supersession,
    restated,
)
from code_factory.memory_extras.service.page import PageMixin
from code_factory.memory_extras.service.recall import applied
from code_factory.platform.errors import BadRequestError, ConflictError
from code_factory.platform.text import epoch_day


class AdmissionMixin(PageMixin):
    """The memory service's admission, and the question a new ticket asks."""

    async def prepare_admission(self, draft: NewMemory, _intake: Intake) -> Admission:
        """Refuse a draft on what files and git say, and return the check that reads the store.

        Called before the write's transaction opens, so the CLAUDE.md read and the scan for
        defined tests hold no connection and no lock. The returned check runs under the
        repository's lock.

        Raises:
            BadRequestError: A field is refused or CLAUDE.md says it.
        """
        refusal = check_fields(draft.kind, draft.statement, draft)
        if refusal is not None:
            raise BadRequestError(refusal)
        root = await self._root_if_tracked(draft.repository)
        claude = "" if root is None else await self._files.claude_md(root)
        said = restated(draft.statement, claude)
        if said is not None:
            raise BadRequestError(f"restates CLAUDE.md line {said[0]}: {said[1]}")
        defined = await self._defined_for(draft)
        return lambda d, i: self._admit(d, i, defined)

    async def _defined_for(self, draft: NewMemory) -> frozenset[str]:
        entries = await self._memory.list_entries(draft.repository, include_retired=True)
        return await self._defined(draft.repository, [e for e in entries if not e.retired])

    async def _admit(self, draft: NewMemory, intake: Intake, defined: frozenset[str]) -> None:
        """The budget, the ids a draft supersedes and (when asked) the pair check.

        Raises:
            BadRequestError: The budget would pass, or a superseded id is no entry.
            ConflictError: An active entry is on the draft's subject.
        """
        view = await self._view(draft.repository, intake.now, defined)
        today = intake.now.date()
        entry = draft_entry(draft, today, proposed=intake.proposed)
        if entry.kind != "lesson" and everywhere(entry):
            retiring = set() if intake.proposed else set(draft.supersedes)
            every = [a.entry for a in applied(view, TicketContext()) if a.entry.id not in retiring]
            refused = over_budget([*every, entry])
            if refused is not None:
                raise BadRequestError(refused)
        active = {e.id for e in view.entries if not e.retired}
        retired = {e.id for e in view.entries if e.retired}
        plan_supersession("", draft.supersedes, active, retired)
        if intake.check_pairs and not intake.keep_both:
            partner = paired_with(entry, view.current, view.defined, epoch_day(intake.now))
            if partner is not None:
                msg = (
                    f"it is on the subject of {partner}: pass --supersedes {partner} or --keep-both"
                )
                raise ConflictError(msg)

    async def duplicate_questions(self, repository: str, title: str) -> list[DuplicateQuestion]:
        """A question for each open ticket whose title the new ticket's looks like."""
        return duplicate_questions(title, await self._tickets.open_titles(repository))

    @staticmethod
    def alike(one: str, other: str) -> bool:
        """Whether two titles look like one another."""
        return alike(one, other)

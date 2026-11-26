"""Releases through the release service, against the test database.

The notes layout and the version form are the previous implementation's (`release_notes_are_
drafted_once`, `a_version_is_three_numbers`); the states and refusals are the commands spec's
`ReleaseService` table.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError, ConflictError, NotFoundError
from code_factory.releases.models import ReleaseState
from code_factory.releases.service import ReleaseService
from code_factory.tickets.models import NewTicket, Ticket, TicketType
from code_factory.tickets.service import TicketService
from ticket_values import NOW, OWNER

REPO = "sample"
LATER = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def releases(uow: UnitOfWork, tickets: TicketService) -> ReleaseService:
    return ReleaseService(uow, tickets, clock=lambda: LATER)


async def merged(
    tickets: TicketService, title: str, kind: TicketType = "feature", repository: str = REPO
) -> Ticket:
    made = await tickets.create(NewTicket(repository=repository, title=title, type=kind), by=OWNER)
    return await tickets.set_merged(made.id, True, by=OWNER)


async def test_a_draft_lists_the_merged_tickets_by_section(
    releases: ReleaseService, tickets: TicketService
) -> None:
    fix = await merged(tickets, "Fix a crash", "bug")
    page = await merged(tickets, "Add a page")
    await tickets.create(NewTicket(repository=REPO, title="Not merged yet"), by=OWNER)
    await merged(tickets, "Elsewhere", repository="other")
    drafted = await releases.draft(REPO, "1.2.0", by=OWNER)
    assert drafted.notes == (
        f"# 1.2.0\n\n## Added\n- {page.id}: Add a page\n\n## Fixed\n- {fix.id}: Fix a crash\n"
    )
    assert (drafted.repository, drafted.version, drafted.state) == (
        REPO,
        "1.2.0",
        ReleaseState.DRAFT,
    )
    assert (drafted.drafted_at, drafted.published_at, drafted.tickets) == (LATER, None, [])


async def test_a_draft_of_a_repository_with_nothing_merged_says_so(
    releases: ReleaseService,
) -> None:
    drafted = await releases.draft("empty", "0.1.0", by=OWNER)
    assert drafted.notes == "# 0.1.0\n\nNothing merged since the last release.\n"


async def test_a_draft_leaves_out_tickets_an_earlier_release_names(
    releases: ReleaseService, tickets: TicketService
) -> None:
    old = await merged(tickets, "Shipped already")
    await releases.draft(REPO, "0.1.0", by=OWNER)
    await releases.publish(REPO, "0.1.0", by=OWNER)
    new = await merged(tickets, "Fresh")
    drafted = await releases.draft(REPO, "0.2.0", by=OWNER)
    assert f"- {new.id}: Fresh" in drafted.notes
    assert old.id not in drafted.notes


async def test_a_draft_still_lists_tickets_only_a_draft_names(
    releases: ReleaseService, tickets: TicketService
) -> None:
    one = await merged(tickets, "In a draft")
    await releases.draft(REPO, "0.1.0", by=OWNER)
    drafted = await releases.draft(REPO, "0.2.0", by=OWNER)
    assert f"- {one.id}: In a draft" in drafted.notes


async def test_a_version_is_drafted_once(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    with pytest.raises(
        ConflictError, match=r"1\.0\.0 exists; a released version is immutable, draft the next one"
    ):
        await releases.draft(REPO, "1.0.0", by=OWNER)


async def test_the_same_version_of_another_repository_is_its_own_release(
    releases: ReleaseService,
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    assert (await releases.draft("other", "1.0.0", by=OWNER)).repository == "other"


@pytest.mark.parametrize("bad", ["1.0", "1.2.0-rc.1", "v1.0.0", "", "1.0.0\n"])
async def test_a_draft_needs_a_version_of_three_numbers(releases: ReleaseService, bad: str) -> None:
    with pytest.raises(BadRequestError, match=r"is not a version MAJOR\.MINOR\.PATCH"):
        await releases.draft(REPO, bad, by=OWNER)


async def test_a_draft_needs_a_repository(releases: ReleaseService) -> None:
    with pytest.raises(BadRequestError, match="a release needs a repository"):
        await releases.draft("", "1.0.0", by=OWNER)


async def test_a_drafts_notes_can_be_edited(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    edited = await releases.edit_notes(REPO, "1.0.0", "# 1.0.0\n\nMy words.\n", by=OWNER)
    assert edited.notes == "# 1.0.0\n\nMy words.\n"
    assert (await releases.get(REPO, "1.0.0")).notes == "# 1.0.0\n\nMy words.\n"


async def test_published_notes_are_final(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    with pytest.raises(ConflictError, match=r"1\.0\.0 is published: its notes are final"):
        await releases.edit_notes(REPO, "1.0.0", "changed", by=OWNER)
    assert (await releases.get(REPO, "1.0.0")).notes.startswith("# 1.0.0")


async def test_editing_a_release_that_was_never_drafted_says_how_to_draft_it(
    releases: ReleaseService,
) -> None:
    with pytest.raises(
        NotFoundError,
        match=r"no release 9\.9\.9 of sample: draft it with code-factory release draft 9\.9\.9",
    ):
        await releases.edit_notes(REPO, "9.9.9", "x", by=OWNER)


async def test_notes_over_the_limit_are_refused_and_the_limit_itself_is_taken(
    releases: ReleaseService,
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.edit_notes(REPO, "1.0.0", "x" * 100_000, by=OWNER)
    with pytest.raises(BadRequestError, match="notes are 100001 characters; the limit is 100000"):
        await releases.edit_notes(REPO, "1.0.0", "x" * 100_001, by=OWNER)


async def test_publishing_names_the_tickets_the_notes_mention(
    releases: ReleaseService, tickets: TicketService
) -> None:
    first = await merged(tickets, "One")
    await releases.draft(REPO, "1.0.0", by=OWNER)
    notes = f"# 1.0.0\n\nSee {first.id}, CF-90000001 and XCF-90000002 and CF-900000030.\n"
    await releases.edit_notes(REPO, "1.0.0", notes, by=OWNER)
    published = await releases.publish(REPO, "1.0.0", by=OWNER)
    assert (published.state, published.published_at) == (ReleaseState.PUBLISHED, LATER)
    assert published.tickets == [first.id, "CF-90000001", "CF-900000030"]


async def test_a_second_publish_is_refused(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    first = await releases.publish(REPO, "1.0.0", by=OWNER)
    with pytest.raises(ConflictError, match=r"1\.0\.0 is published already"):
        await releases.publish(REPO, "1.0.0", by=OWNER)
    assert await releases.get(REPO, "1.0.0") == first


async def test_publishing_an_unknown_release_is_not_found(releases: ReleaseService) -> None:
    with pytest.raises(NotFoundError, match=r"no release 1\.0\.0 of sample"):
        await releases.publish(REPO, "1.0.0", by=OWNER)


async def test_naming_answers_published_releases_and_not_drafts(
    releases: ReleaseService, tickets: TicketService
) -> None:
    shipped = await merged(tickets, "Shipped")
    await releases.draft(REPO, "1.0.0", by=OWNER)
    refs = [(REPO, shipped.id), ("other", shipped.id), (REPO, "CF-424242")]
    assert await releases.naming(refs) == {}
    await releases.publish(REPO, "1.0.0", by=OWNER)
    named = await releases.naming(refs)
    assert list(named) == [(REPO, shipped.id)]
    assert (named[REPO, shipped.id].version, named[REPO, shipped.id].published_at) == (
        "1.0.0",
        LATER,
    )


async def test_naming_never_answers_a_pair_the_caller_did_not_ask_for(
    releases: ReleaseService,
) -> None:
    await releases.draft("other", "1.0.0", by=OWNER)
    await releases.edit_notes("other", "1.0.0", "# 1.0.0\n\nCF-5\n", by=OWNER)
    await releases.publish("other", "1.0.0", by=OWNER)
    assert await releases.naming([(REPO, "CF-5"), ("other", "CF-6")]) == {}


async def test_the_tickets_a_release_names_are_listed_by_number(
    releases: ReleaseService,
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.edit_notes(REPO, "1.0.0", "# 1.0.0\n\nCF-10 CF-9 CF-100\n", by=OWNER)
    published = await releases.publish(REPO, "1.0.0", by=OWNER)
    assert published.tickets == ["CF-9", "CF-10", "CF-100"]
    assert (await releases.get(REPO, "1.0.0")).tickets == ["CF-9", "CF-10", "CF-100"]


async def test_a_ticket_two_releases_name_belongs_to_the_one_published_first(
    releases: ReleaseService, tickets: TicketService, uow: UnitOfWork
) -> None:
    one = await merged(tickets, "Twice")
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.draft(REPO, "1.1.0", by=OWNER)
    await releases.edit_notes(REPO, "1.1.0", f"# 1.1.0\n\n{one.id}\n", by=OWNER)
    earlier = ReleaseService(uow, tickets, clock=lambda: NOW)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    await earlier.publish(REPO, "1.1.0", by=OWNER)
    assert (await releases.naming([(REPO, one.id)]))[REPO, one.id].version == "1.1.0"


async def test_naming_a_thousand_tickets_is_one_statement(
    releases: ReleaseService, connection: AsyncConnection
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    notes = "# 1.0.0\n\n" + " ".join(f"CF-{n}" for n in range(1, 1001)) + "\n"
    await releases.edit_notes(REPO, "1.0.0", notes, by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    seen: list[str] = []

    def record(_c: object, _cur: object, statement: str, *_rest: object) -> None:
        seen.append(statement)

    event.listen(connection.sync_engine, "before_cursor_execute", record)
    try:
        named = await releases.naming([(REPO, f"CF-{n}") for n in range(1, 1001)])
    finally:
        event.remove(connection.sync_engine, "before_cursor_execute", record)
    assert len(named) == 1000
    assert len([s for s in seen if s.lstrip().upper().startswith("SELECT")]) == 1


async def test_naming_nothing_asks_nothing(releases: ReleaseService) -> None:
    assert await releases.naming([]) == {}


async def test_releases_list_by_repository_newest_version_first(
    releases: ReleaseService,
) -> None:
    for repository, version in [(REPO, "0.9.0"), (REPO, "0.10.0"), ("other", "0.1.0")]:
        await releases.draft(repository, version, by=OWNER)
    assert [(r.repository, r.version) for r in await releases.list(REPO)] == [
        (REPO, "0.10.0"),
        (REPO, "0.9.0"),
    ]
    assert [(r.repository, r.version) for r in await releases.list(None)] == [
        ("other", "0.1.0"),
        (REPO, "0.10.0"),
        (REPO, "0.9.0"),
    ]


async def test_a_published_release_lists_the_tickets_it_names(
    releases: ReleaseService, tickets: TicketService
) -> None:
    one = await merged(tickets, "One")
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    await releases.draft(REPO, "1.1.0", by=OWNER)
    listed = {r.version: r.tickets for r in await releases.list(REPO)}
    assert listed == {"1.0.0": [one.id], "1.1.0": []}


async def test_getting_an_unknown_release_is_not_found(releases: ReleaseService) -> None:
    with pytest.raises(NotFoundError, match=r"no release 1\.0\.0 of sample"):
        await releases.get(REPO, "1.0.0")


async def test_the_tag_is_recorded_before_the_push_and_the_push_after(
    releases: ReleaseService,
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    pending = await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER)
    assert (pending.state, pending.tag_commit, pending.tagged_at) == (
        ReleaseState.PUBLISHED,
        COMMIT,
        None,
    )
    done = await releases.record_tagged(REPO, "1.0.0", by=OWNER)
    assert (done.state, done.tag_commit, done.tagged_at) == (ReleaseState.TAGGED, COMMIT, LATER)


async def test_recording_the_same_commit_again_changes_nothing(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    first = await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER)
    assert await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER) == first


async def test_a_recorded_commit_is_never_replaced(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER)
    with pytest.raises(ConflictError, match=r"1\.0\.0 is tagged on 0123456, not on fedcba9"):
        await releases.record_tag_commit(REPO, "1.0.0", "fedcba9" + COMMIT[7:], by=OWNER)


async def test_a_draft_cannot_be_tagged(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    with pytest.raises(ConflictError, match=r"1\.0\.0 is a draft: publish it first"):
        await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER)


async def test_a_commit_that_is_not_a_full_hash_is_refused(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    for bad in ["abc123", COMMIT.upper(), COMMIT + "0"]:
        with pytest.raises(BadRequestError, match="is not a full commit hash"):
            await releases.record_tag_commit(REPO, "1.0.0", bad, by=OWNER)
    sha256 = COMMIT + "0123456789abcdef0123456789abcdef0123456789abcdef"[:24]
    assert (await releases.record_tag_commit(REPO, "1.0.0", sha256, by=OWNER)).tag_commit == sha256


async def test_tagging_is_recorded_only_after_a_commit(releases: ReleaseService) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    with pytest.raises(ConflictError, match=r"1\.0\.0 has no tag commit recorded"):
        await releases.record_tagged(REPO, "1.0.0", by=OWNER)


async def test_recording_the_push_twice_keeps_the_first_time(
    releases: ReleaseService, uow: UnitOfWork, tickets: TicketService
) -> None:
    await releases.draft(REPO, "1.0.0", by=OWNER)
    await releases.publish(REPO, "1.0.0", by=OWNER)
    await releases.record_tag_commit(REPO, "1.0.0", COMMIT, by=OWNER)
    first = await releases.record_tagged(REPO, "1.0.0", by=OWNER)
    later = ReleaseService(uow, tickets, clock=lambda: datetime(2027, 1, 1, tzinfo=UTC))
    assert await later.record_tagged(REPO, "1.0.0", by=OWNER) == first


async def test_the_newest_release_is_the_highest_tagged_version(
    releases: ReleaseService,
) -> None:
    assert await releases.newest(REPO) is None
    for version in ["0.9.0", "0.10.0", "1.0.0"]:
        await releases.draft(REPO, version, by=OWNER)
        await releases.publish(REPO, version, by=OWNER)
    for version in ["0.9.0", "0.10.0"]:
        await releases.record_tag_commit(REPO, version, COMMIT, by=OWNER)
        await releases.record_tagged(REPO, version, by=OWNER)
    await releases.draft(REPO, "2.0.0", by=OWNER)
    newest = await releases.newest(REPO)
    assert newest is not None
    assert newest.version == "0.10.0"


async def test_a_draft_lists_tickets_of_a_type_by_number_not_by_board_rank(
    releases: ReleaseService, tickets: TicketService
) -> None:
    first = await tickets.create(NewTicket(repository=REPO, title="First", rank=2), by=OWNER)
    second = await tickets.create(NewTicket(repository=REPO, title="Second", rank=1), by=OWNER)
    for made in (first, second):
        await tickets.set_merged(made.id, True, by=OWNER)
    drafted = await releases.draft(REPO, "1.0.0", by=OWNER)
    assert drafted.notes == (f"# 1.0.0\n\n## Added\n- {first.id}: First\n- {second.id}: Second\n")


async def test_a_draft_lists_archived_merged_tickets(
    releases: ReleaseService, tickets: TicketService
) -> None:
    old = await merged(tickets, "Archived after merging")
    await tickets.archive(old.id, by=OWNER)
    drafted = await releases.draft(REPO, "1.0.0", by=OWNER)
    assert f"- {old.id}: Archived after merging" in drafted.notes


async def test_another_repositorys_release_does_not_hide_a_ticket(
    releases: ReleaseService, tickets: TicketService
) -> None:
    mine = await merged(tickets, "Mine")
    await releases.draft("other", "1.0.0", by=OWNER)
    await releases.edit_notes("other", "1.0.0", f"Names {mine.id}.\n", by=OWNER)
    await releases.publish("other", "1.0.0", by=OWNER)
    drafted = await releases.draft(REPO, "1.0.0", by=OWNER)
    assert f"- {mine.id}: Mine" in drafted.notes

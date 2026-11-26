"""The broker's rows: what is stored, and each compare-and-set on them."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from code_factory.broker.repository import SWEEP_LOCK, BrokerRepository
from code_factory.platform.config import Settings
from code_factory.platform.db import create_engine

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
DIGEST = "a" * 64


@pytest.fixture
def repo(db_session: AsyncSession) -> BrokerRepository:
    return BrokerRepository(db_session)


async def add(
    repo: BrokerRepository, run: str = "r1", digest: str = DIGEST, **more: object
) -> None:
    fields = {"connection": "main", "cap_usd": None, "created_at": NOW, "expires_at": LATER}
    assert await repo.add(digest, run, **{**fields, **more})  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


async def test_a_row_is_found_by_digest_and_by_run(repo: BrokerRepository) -> None:
    await add(repo, cap_usd=Decimal("2.5"))
    by_digest = await repo.by_digest(DIGEST)
    assert by_digest is not None
    assert (by_digest.run_id, by_digest.connection, by_digest.cap_usd) == (
        "r1",
        "main",
        Decimal("2.5"),
    )
    assert by_digest.key_state == "none"
    assert await repo.by_run("r1") == by_digest
    assert await repo.by_digest("b" * 64) is None


async def test_a_second_row_for_one_run_is_refused_without_an_error(repo: BrokerRepository) -> None:
    await add(repo)
    assert not await repo.add("b" * 64, "r1", "main", None, NOW, LATER)


async def test_a_digest_that_is_not_sha256_hex_is_refused_by_the_database(
    repo: BrokerRepository,
) -> None:
    with pytest.raises(DBAPIError, match="digest_is_sha256_hex"):
        await repo.add("A" * 64, "r1", None, None, NOW, LATER)


@pytest.mark.parametrize("cap", [Decimal(-1), Decimal(1_000_000)])
async def test_a_cap_outside_the_range_is_refused_by_the_database(
    repo: BrokerRepository, cap: Decimal
) -> None:
    with pytest.raises(DBAPIError, match="cap_in_range"):
        await repo.add(DIGEST, "r1", "main", cap, NOW, LATER)


async def test_the_largest_cap_is_stored(repo: BrokerRepository) -> None:
    await add(repo, cap_usd=Decimal("999999.9999"))
    row = await repo.by_run("r1")
    assert row is not None
    assert row.cap_usd == Decimal("999999.9999")


async def test_ending_twice_keeps_the_first_time(repo: BrokerRepository) -> None:
    await add(repo)
    first = await repo.end("r1", NOW)
    second = await repo.end("r1", LATER)
    assert first is not None
    assert second is not None
    assert second.ended_at == NOW
    assert await repo.end("nobody", NOW) is None


async def test_a_row_without_a_key_is_deleted_and_one_with_a_key_is_not(
    repo: BrokerRepository,
) -> None:
    await add(repo, "plain", "a" * 64)
    await add(repo, "keyed", "b" * 64)
    assert await repo.set_state("keyed", ("none",), "making", NOW)
    assert await repo.set_state("keyed", ("making",), "made", NOW, "kid-1")
    assert await repo.delete_without_key("plain")
    assert not await repo.delete_without_key("keyed")
    assert await repo.by_run("keyed") is not None


async def test_the_state_moves_only_from_the_state_it_was_read_in(repo: BrokerRepository) -> None:
    await add(repo)
    assert await repo.set_state("r1", ("none",), "making", NOW)
    assert not await repo.set_state("r1", ("none",), "making", NOW)
    assert not await repo.set_state("r1", ("none",), "refused", NOW)


async def test_a_made_state_needs_an_id_and_no_other_state_may_have_one(
    repo: BrokerRepository,
) -> None:
    await add(repo)
    with pytest.raises(DBAPIError, match="made_key_has_an_id"):
        await repo.set_state("r1", ("none",), "made", NOW)


async def test_the_sweep_deletes_dead_rows_without_a_key_only(repo: BrokerRepository) -> None:
    await add(repo, "ended", "a" * 64)
    await add(repo, "expired", "b" * 64, expires_at=NOW)
    await add(repo, "live", "c" * 64)
    await add(repo, "keyed", "d" * 64, expires_at=NOW)
    await repo.set_state("keyed", ("none",), "making", NOW)
    await repo.end("ended", NOW)
    assert await repo.delete_dead_without_key(NOW) == 2
    assert await repo.by_run("live") is not None
    assert await repo.by_run("keyed") is not None


async def test_live_runs_are_those_neither_ended_nor_expired(repo: BrokerRepository) -> None:
    await add(repo, "live", "a" * 64)
    await add(repo, "ended", "b" * 64)
    await add(repo, "expired", "c" * 64, expires_at=NOW)
    await repo.end("ended", NOW)
    assert await repo.live_run_ids(NOW) == ["live"]
    assert await repo.end_runs(["live", "ended", "ghost"], NOW) == 1


async def test_a_dead_made_row_is_claimed_once_until_its_claim_goes_stale(
    repo: BrokerRepository,
) -> None:
    await add(repo, expires_at=NOW)
    await repo.set_state("r1", ("none",), "making", NOW)
    await repo.set_state("r1", ("making",), "made", NOW, "kid-1")
    first = await repo.claim_deletes(NOW, NOW - timedelta(seconds=30))
    assert [row.run_id for row in first] == ["r1"]
    assert await repo.claim_deletes(NOW, NOW - timedelta(seconds=30)) == []
    later = NOW + timedelta(seconds=31)
    assert [
        row.run_id for row in await repo.claim_deletes(later, later - timedelta(seconds=30))
    ] == ["r1"]


async def test_a_confirmed_delete_removes_the_row_and_a_failed_one_keeps_it_with_the_sentence(
    repo: BrokerRepository,
) -> None:
    await add(repo, expires_at=NOW)
    await repo.set_state("r1", ("none",), "making", NOW)
    await repo.set_state("r1", ("making",), "made", NOW, "kid-1")
    [row] = await repo.claim_deletes(NOW, NOW)
    await repo.release_failed(row.id, NOW, "the provider did not answer")
    kept = await repo.by_run("r1")
    assert kept is not None
    assert (kept.key_delete_error, kept.key_delete_failed_at) == (
        "the provider did not answer",
        NOW,
    )
    assert not await repo.delete_made(row.id, "another-id")
    assert await repo.delete_made(row.id, "kid-1")
    assert await repo.by_run("r1") is None


async def test_a_making_row_turns_refused_only_when_older_than_the_cutoff(
    repo: BrokerRepository,
) -> None:
    await add(repo, "old", "a" * 64)
    await add(repo, "young", "b" * 64)
    await repo.set_state("old", ("none",), "making", NOW - timedelta(minutes=3))
    await repo.set_state("young", ("none",), "making", NOW - timedelta(minutes=1))
    assert await repo.refuse_stale_making(NOW - timedelta(minutes=2), NOW) == 1
    old, young = await repo.by_run("old"), await repo.by_run("young")
    assert old is not None
    assert young is not None
    assert (old.key_state, young.key_state) == ("refused", "making")


async def test_counts_and_listing_tell_live_from_waiting(repo: BrokerRepository) -> None:
    await add(repo, "live", "a" * 64)
    await add(repo, "held", "b" * 64)
    await add(repo, "pending", "c" * 64, expires_at=NOW)
    await add(repo, "gone", "d" * 64, expires_at=NOW)
    for run in ("held", "pending"):
        await repo.set_state(run, ("none",), "making", NOW)
        await repo.set_state(run, ("making",), "made", NOW, f"kid-{run}")
    assert await repo.counts(NOW) == (2, 2, 1)
    assert [row.run_id for row in await repo.listed(NOW)] == ["live", "held", "pending"]


async def test_the_sweep_lock_is_refused_while_another_connection_holds_it(
    repo: BrokerRepository, settings: Settings
) -> None:
    engine = create_engine(settings)
    try:
        async with engine.connect() as other:
            await other.execute(text(f"SELECT pg_advisory_xact_lock({SWEEP_LOCK})"))
            assert not await repo.take_sweep_lock()
            await other.rollback()
        assert await repo.take_sweep_lock()
    finally:
        await engine.dispose()


async def test_nothing_in_the_table_is_wider_than_digests_and_ids(db_session: AsyncSession) -> None:
    columns = await db_session.scalars(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'broker_tokens' AND table_schema = current_schema() "
            "ORDER BY column_name"
        )
    )
    assert sorted(columns) == sorted(
        [
            "id", "digest", "run_id", "connection", "cap_usd", "key_state", "run_key_id",
            "created_at", "expires_at", "ended_at", "key_state_at", "delete_claimed_at",
            "key_delete_failed_at", "key_delete_error",
        ]
    )  # fmt: skip

import hashlib
from datetime import timedelta
from typing import Any, override

import pytest
from auth_clock import START, Clock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from code_factory.auth.models import TokenKind
from code_factory.auth.service import AuthService
from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.platform.identity import Role

HOUR = timedelta(hours=1)


def _unit_of_work(
    connection: AsyncConnection, session_class: type[AsyncSession] = AsyncSession
) -> UnitOfWork:
    return UnitOfWork(
        async_sessionmaker(
            bind=connection,
            class_=session_class,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def auth(connection: AsyncConnection, clock: Clock) -> AuthService:
    return AuthService(_unit_of_work(connection), clock=clock)


async def _issue_run(auth: AuthService, run_id: str = "run-1", ticket: str | None = "CF-12") -> str:
    issued = await auth.issue_run_token(
        run_id=run_id, ticket_id=ticket, stage="build", repository="/repo", lifetime=HOUR
    )
    return issued.token.get_secret_value()


async def test_a_run_token_verifies_to_an_actor_bound_to_its_run_and_ticket(
    auth: AuthService,
) -> None:
    token = await _issue_run(auth)
    assert token.startswith("cfr_")
    actor = await auth.verify_token(token)
    assert actor is not None
    assert (actor.role, actor.subject, actor.run_id, actor.ticket_id, actor.stage) == (
        Role.RUN,
        "run:run-1",
        "run-1",
        "CF-12",
        "build",
    )
    assert actor.repository == "/repo"
    assert actor.expires_at == START + HOUR


async def test_a_run_token_without_a_ticket_is_a_coordinator(auth: AuthService) -> None:
    actor = await auth.verify_token(await _issue_run(auth, ticket=None))
    assert actor is not None
    assert (actor.role, actor.ticket_id) == (Role.COORDINATOR, None)


async def test_an_owner_token_verifies_to_the_owner_named_by_its_label(auth: AuthService) -> None:
    issued = await auth.issue_owner_token("alex laptop", lifetime=timedelta(days=30))
    token = issued.token.get_secret_value()
    assert token.startswith("cfo_")
    actor = await auth.verify_token(token)
    assert actor is not None
    assert (actor.role, actor.subject, actor.run_id, actor.ticket_id) == (
        Role.OWNER,
        "owner:alex laptop",
        None,
        None,
    )


@pytest.mark.parametrize("label", ["", "   ", "x" * 65, "line\nbreak"])
async def test_an_owner_label_must_be_one_short_printable_line(
    auth: AuthService, label: str
) -> None:
    with pytest.raises(BadRequestError, match="label"):
        await auth.issue_owner_token(label, lifetime=HOUR)


async def test_only_the_digest_is_stored_never_the_token(
    auth: AuthService, connection: AsyncConnection
) -> None:
    token = await _issue_run(auth)
    rows = (await connection.execute(text("select * from auth_tokens"))).all()
    assert len(rows) == 1
    assert hashlib.sha256(token.encode()).hexdigest() in rows[0]
    assert token not in " ".join(str(value) for value in rows[0])


async def test_the_issued_token_does_not_print_its_value(auth: AuthService) -> None:
    issued = await auth.issue_run_token(
        run_id="r", ticket_id="CF-1", stage="spec", repository="/r", lifetime=HOUR
    )
    assert issued.token.get_secret_value() not in repr(issued)
    assert issued.token.get_secret_value() not in issued.model_dump_json()


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "cfr_" + "A" * 43, "cfo_" + "B" * 43],
)
async def test_an_unknown_or_malformed_token_verifies_to_nothing(
    auth: AuthService, token: str
) -> None:
    assert await auth.verify_token(token) is None


async def test_a_token_is_live_until_its_expiry_instant(auth: AuthService, clock: Clock) -> None:
    token = await _issue_run(auth)
    clock.advance(HOUR - timedelta(microseconds=1))
    assert await auth.verify_token(token) is not None
    clock.advance(timedelta(microseconds=1))
    assert await auth.verify_token(token) is None


async def test_a_revoked_token_verifies_to_nothing_and_revoking_twice_says_so(
    auth: AuthService,
) -> None:
    issued = await auth.issue_owner_token("a", lifetime=HOUR)
    assert await auth.revoke(issued.id) is True
    assert await auth.verify_token(issued.token.get_secret_value()) is None
    assert await auth.revoke(issued.id) is False
    assert await auth.revoke(issued.id + 1000) is False


async def test_revoking_a_run_ends_every_token_of_that_run_and_only_those(
    auth: AuthService,
) -> None:
    first = await _issue_run(auth, "run-1")
    second = await _issue_run(auth, "run-1")
    other = await _issue_run(auth, "run-2")
    assert await auth.revoke_run("run-1") == 2
    assert await auth.verify_token(first) is None
    assert await auth.verify_token(second) is None
    assert await auth.verify_token(other) is not None
    assert await auth.revoke_run("run-1") == 0


async def test_revoking_a_run_counts_only_tokens_that_were_still_live(
    auth: AuthService, clock: Clock
) -> None:
    await _issue_run(auth, "run-1")
    clock.advance(HOUR)
    assert await auth.revoke_run("run-1") == 0


async def test_expiry_is_judged_when_the_database_is_reached_not_before_the_pool_answers(
    connection: AsyncConnection, clock: Clock
) -> None:
    class SlowToConnect(AsyncSession):
        """A session whose connection arrives an hour late, as when the pool is exhausted."""

        @override
        async def connection(
            self, *args: Any, **kwargs: Any
        ) -> AsyncConnection:  # mirrors SQLAlchemy's signature
            clock.advance(HOUR)
            return await super().connection(*args, **kwargs)

    patient = AuthService(_unit_of_work(connection, SlowToConnect), clock=clock)
    prompt = AuthService(_unit_of_work(connection), clock=clock)
    token = await _issue_run(prompt)  # lasts one hour
    assert await patient.verify_token(token) is None


async def test_is_live_follows_revocation_and_expiry(auth: AuthService, clock: Clock) -> None:
    issued = await auth.issue_owner_token("a", lifetime=HOUR)
    assert await auth.is_live(issued.id) is True
    clock.advance(HOUR)
    assert await auth.is_live(issued.id) is False
    fresh = await auth.issue_owner_token("b", lifetime=HOUR)
    await auth.revoke(fresh.id)
    assert await auth.is_live(fresh.id) is False
    assert await auth.is_live(fresh.id + 1000) is False


async def test_a_token_is_accepted_only_as_the_kinds_the_caller_names(auth: AuthService) -> None:
    run = await _issue_run(auth)
    owner = (await auth.issue_owner_token("a", lifetime=HOUR)).token.get_secret_value()
    assert await auth.verify_token(run, kinds={TokenKind.OWNER}) is None
    assert await auth.verify_token(owner, kinds={TokenKind.RUN}) is None
    assert await auth.verify_token(run, kinds={TokenKind.RUN}) is not None
    assert await auth.verify_token(owner, kinds={TokenKind.RUN, TokenKind.OWNER}) is not None


async def test_a_sign_in_nonce_is_exchanged_once_for_an_owner_session(auth: AuthService) -> None:
    nonce = await auth.issue_sign_in_nonce("alex")
    value = nonce.token.get_secret_value()
    assert value.startswith("cfn_")
    session = await auth.redeem_sign_in_nonce(value, lifetime=timedelta(days=30))
    assert session is not None
    cookie = session.token.get_secret_value()
    assert cookie.startswith("cfs_")
    actor = await auth.verify_token(cookie, kinds={TokenKind.SESSION})
    assert actor is not None
    assert (actor.role, actor.subject) == (Role.OWNER, "owner:alex")
    assert await auth.redeem_sign_in_nonce(value, lifetime=timedelta(days=30)) is None


async def test_a_nonce_expires_and_is_never_a_bearer_or_a_session(
    auth: AuthService, clock: Clock
) -> None:
    value = (await auth.issue_sign_in_nonce("alex")).token.get_secret_value()
    assert await auth.verify_token(value) is None
    assert await auth.verify_token(value, kinds={TokenKind.SESSION}) is None
    assert await auth.verify_token(value, kinds=set(TokenKind)) is None
    clock.advance(timedelta(seconds=61))
    assert await auth.redeem_sign_in_nonce(value, lifetime=HOUR) is None


async def test_a_session_is_not_a_bearer_for_mcp(auth: AuthService) -> None:
    nonce = (await auth.issue_sign_in_nonce("alex")).token.get_secret_value()
    session = await auth.redeem_sign_in_nonce(nonce, lifetime=HOUR)
    assert session is not None
    assert await auth.verify_token(session.token.get_secret_value()) is None


async def test_a_session_token_cannot_be_redeemed_as_a_nonce(auth: AuthService) -> None:
    await auth.issue_sign_in_nonce("alex")
    owner = (await auth.issue_owner_token("a", lifetime=HOUR)).token.get_secret_value()
    assert await auth.redeem_sign_in_nonce(owner, lifetime=HOUR) is None


async def test_verifying_records_the_last_use_at_most_once_a_minute(
    auth: AuthService, clock: Clock
) -> None:
    issued = await auth.issue_owner_token("a", lifetime=timedelta(days=1))
    token = issued.token.get_secret_value()
    await auth.verify_token(token)
    first = (await auth.list_tokens())[0].last_used_at
    assert first == START
    clock.advance(timedelta(seconds=59))
    await auth.verify_token(token)
    assert (await auth.list_tokens())[0].last_used_at == START
    clock.advance(timedelta(seconds=1))
    await auth.verify_token(token)
    assert (await auth.list_tokens())[0].last_used_at == START + timedelta(seconds=60)


async def test_listing_shows_live_tokens_without_values_and_can_include_ended_ones(
    auth: AuthService, clock: Clock
) -> None:
    live = await auth.issue_owner_token("live", lifetime=timedelta(days=2))
    gone = await auth.issue_owner_token("gone", lifetime=timedelta(days=2))
    await auth.revoke(gone.id)
    clock.advance(timedelta(days=1))
    listed = await auth.list_tokens()
    assert [(info.id, info.label, info.kind) for info in listed] == [
        (live.id, "live", TokenKind.OWNER)
    ]
    everything = await auth.list_tokens(include_ended=True)
    assert {info.id for info in everything} == {live.id, gone.id}
    assert not any(hasattr(info, "digest") or hasattr(info, "token") for info in everything)


async def test_describe_names_what_the_actor_is(auth: AuthService) -> None:
    actor = await auth.verify_token(await _issue_run(auth))
    assert actor is not None
    described = auth.describe(actor)
    assert (described.role, described.subject, described.run_id, described.ticket_id) == (
        Role.RUN,
        "run:run-1",
        "run-1",
        "CF-12",
    )
    assert (described.stage, described.repository) == ("build", "/repo")
    assert described.expires_at == actor.expires_at


async def test_sweeping_deletes_tokens_that_ended_more_than_a_day_ago_and_keeps_the_rest(
    auth: AuthService, clock: Clock
) -> None:
    expired = await auth.issue_owner_token("expired", lifetime=HOUR)  # ends at +1h
    revoked = await auth.issue_owner_token("revoked", lifetime=timedelta(days=30))
    await auth.revoke(revoked.id)  # ends at +0
    kept = await auth.issue_owner_token("kept", lifetime=timedelta(days=30))
    clock.advance(timedelta(days=1))
    assert await auth.sweep_expired() == 0  # exactly a day ago is not more than a day
    clock.advance(timedelta(seconds=1))
    assert await auth.sweep_expired() == 1
    assert {info.id for info in await auth.list_tokens(include_ended=True)} == {
        expired.id,
        kept.id,
    }
    clock.advance(HOUR)
    assert await auth.sweep_expired() == 1
    assert {info.id for info in await auth.list_tokens(include_ended=True)} == {kept.id}


async def test_a_run_token_longer_than_a_week_is_refused(auth: AuthService) -> None:
    with pytest.raises(BadRequestError, match="run token lifetime is at most"):
        await auth.issue_run_token(
            run_id="r", ticket_id="CF-1", stage="spec", repository="/r", lifetime=timedelta(days=8)
        )


async def test_listing_and_revoking_can_be_limited_to_some_kinds_of_token(
    auth: AuthService,
) -> None:
    owner = await auth.issue_owner_token("o", lifetime=HOUR)
    run = await auth.issue_run_token(
        run_id="r", ticket_id="CF-1", stage="spec", repository="/r", lifetime=HOUR
    )
    only_owners = {TokenKind.OWNER}
    assert [info.id for info in await auth.list_tokens(kinds=only_owners)] == [owner.id]
    assert await auth.revoke(run.id, kinds=only_owners) is False
    assert await auth.verify_token(run.token.get_secret_value()) is not None
    assert await auth.revoke(owner.id, kinds=only_owners) is True

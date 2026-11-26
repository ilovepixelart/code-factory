"""The broker's table: one row per run that talks to the broker, holding no token and no key.

A token is stored only as its SHA-256 digest and a run key only as the provider's id for it, so
a dump of this table cannot spend money.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db.base import Base

_TZ = DateTime(timezone=True)


class BrokerTokenRow(Base):
    """A run's broker token and the state of its provider key.

    `run_id` names a run with no foreign key: the runs table belongs to another module and this
    row must outlive its run until the provider confirms the key is deleted. `key_state` is
    `making` from the moment the create call starts (a crash then leaves a key whose id is
    unknown), `made` once the id is recorded, `refused` when no key may ever be made for the run.
    `key_state_at` is when the state last changed; `delete_claimed_at` is when a sweep took the
    row to delete its key.
    """

    __tablename__ = "broker_tokens"
    __table_args__ = (
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="digest_is_sha256_hex"),
        CheckConstraint("cap_usd >= 0 AND cap_usd < 1000000", name="cap_in_range"),
        CheckConstraint(
            "key_state IN ('none', 'making', 'made', 'refused')", name="known_key_state"
        ),
        CheckConstraint(
            "(key_state = 'made') = (run_key_id IS NOT NULL)", name="made_key_has_an_id"
        ),
        Index(
            "ix_broker_tokens_pending",
            "expires_at",
            postgresql_where=text("key_state IN ('making', 'made')"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    digest: Mapped[str] = mapped_column(Text, unique=True)
    run_id: Mapped[str] = mapped_column(Text, unique=True)
    connection: Mapped[str | None] = mapped_column(Text, nullable=True)
    cap_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    key_state: Mapped[str] = mapped_column(Text, server_default=text("'none'"))
    run_key_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TZ)
    expires_at: Mapped[datetime] = mapped_column(_TZ)
    ended_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    key_state_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    delete_claimed_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    key_delete_failed_at: Mapped[datetime | None] = mapped_column(_TZ, nullable=True)
    key_delete_error: Mapped[str | None] = mapped_column(Text, nullable=True)

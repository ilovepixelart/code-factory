"""The `auth_tokens` table: digests of issued tokens, never the tokens."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from code_factory.platform.db import Base


class AuthToken(Base):
    """One issued token. `digest` is the SHA-256 hex of the token; the value is not recoverable."""

    __tablename__ = "auth_tokens"
    __table_args__ = (CheckConstraint("kind in ('run', 'owner', 'nonce', 'session')", name="kind"),)

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )  # many rows: bigint identity
    kind: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(Text, unique=True)
    subject: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(Text, index=True)
    ticket_id: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(Text)
    repository: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

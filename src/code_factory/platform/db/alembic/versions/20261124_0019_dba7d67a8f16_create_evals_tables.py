"""Create the evals tables: records, task runs, judgements and judge-day claims.

Revision ID: dba7d67a8f16
Revises: 848da6b68d80
Create Date: 2026-11-24 00:19:29.066519
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dba7d67a8f16"
down_revision: str | Sequence[str] | None = "848da6b68d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_judge_days",
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("repository", "day", name=op.f("pk_eval_judge_days")),
    )
    op.create_table(
        "eval_judgements",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column(
            "findings", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("scorer", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("log", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("cost", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("started_by", sa.Text(), nullable=False),
        sa.CheckConstraint(
            (
                "(kind = 'score' AND score IS NOT NULL AND scorer IS NULL AND answer IS NULL) OR "
                "(kind = 'answer' AND score IS NULL AND scorer IS NOT NULL AND answer IS NOT "
                "NULL)"
            ),
            name=op.f("ck_eval_judgements_shape"),
        ),
        sa.CheckConstraint(
            "answer IS NULL OR answer IN ('yes', 'no', 'unclear')",
            name=op.f("ck_eval_judgements_known_answer"),
        ),
        sa.CheckConstraint(
            "kind IN ('score', 'answer')", name=op.f("ck_eval_judgements_known_kind")
        ),
        sa.CheckConstraint(
            "started_by IN ('owner', 'schedule')", name=op.f("ck_eval_judgements_known_starter")
        ),
        sa.CheckConstraint("cost >= 0", name=op.f("ck_eval_judgements_cost_not_negative")),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 1 AND 5", name=op.f("ck_eval_judgements_score_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_judgements")),
    )
    op.create_index(
        "ix_eval_judgements_answers",
        "eval_judgements",
        ["repository", "scorer", "at"],
        unique=False,
        postgresql_where=sa.text("kind = 'answer'"),
    )
    op.create_index(
        "ix_eval_judgements_scheduled",
        "eval_judgements",
        ["repository", "at"],
        unique=False,
        postgresql_where=sa.text("started_by = 'schedule'"),
    )
    op.create_table(
        "eval_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("repository", sa.Text(), nullable=False),
        sa.Column("set_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("runtime", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("model", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("instructions", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("memory", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("lesson", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("agent", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("connection", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("pass_at_1", sa.Double(), nullable=True),
        sa.Column("pass_k", sa.Double(), nullable=True),
        sa.Column("pass_at_k", sa.Double(), nullable=True),
        sa.Column("caught", sa.Double(), nullable=True),
        sa.Column("false_findings", sa.Double(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Double(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            (
                "(kind = 'build' AND pass_at_1 IS NOT NULL AND pass_k IS NOT NULL AND pass_at_k "
                "IS NOT NULL AND caught IS NULL AND false_findings IS NULL AND failed IS NULL) "
                "OR (kind = 'review' AND caught IS NOT NULL AND false_findings IS NOT NULL AND "
                "failed IS NOT NULL AND pass_at_1 IS NULL AND pass_k IS NULL AND pass_at_k IS "
                "NULL)"
            ),
            name=op.f("ck_eval_records_kind_scores"),
        ),
        sa.CheckConstraint("kind IN ('build', 'review')", name=op.f("ck_eval_records_known_kind")),
        sa.CheckConstraint(
            "stage IN ('spec', 'build', 'review')", name=op.f("ck_eval_records_known_stage")
        ),
        sa.CheckConstraint("cost >= 0", name=op.f("ck_eval_records_cost_not_negative")),
        sa.CheckConstraint("runs > 0", name=op.f("ck_eval_records_runs_positive")),
        sa.CheckConstraint(
            "tokens IS NULL OR tokens >= 0", name=op.f("ck_eval_records_tokens_not_negative")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_records")),
    )
    op.create_index(
        "ix_eval_records_set", "eval_records", ["repository", "set_name", "id"], unique=False
    )
    op.create_table(
        "eval_task_runs",
        sa.Column("record_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("run_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("blocking", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            (
                "(role = 'clean' AND passed IS NULL) OR (role <> 'clean' AND blocking IS NULL "
                "AND passed IS NOT NULL)"
            ),
            name=op.f("ck_eval_task_runs_role_shape"),
        ),
        sa.CheckConstraint(
            "role IN ('build', 'escape', 'clean')", name=op.f("ck_eval_task_runs_known_role")
        ),
        sa.CheckConstraint(
            "blocking IS NULL OR blocking >= 0",
            name=op.f("ck_eval_task_runs_blocking_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["eval_records.id"],
            name=op.f("fk_eval_task_runs_record_id_eval_records"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("record_id", "task_id", "run_no", name=op.f("pk_eval_task_runs")),
    )


def downgrade() -> None:
    op.drop_table("eval_task_runs")
    op.drop_index("ix_eval_records_set", table_name="eval_records")
    op.drop_table("eval_records")
    op.drop_index(
        "ix_eval_judgements_scheduled",
        table_name="eval_judgements",
        postgresql_where=sa.text("started_by = 'schedule'"),
    )
    op.drop_index(
        "ix_eval_judgements_answers",
        table_name="eval_judgements",
        postgresql_where=sa.text("kind = 'answer'"),
    )
    op.drop_table("eval_judgements")
    op.drop_table("eval_judge_days")

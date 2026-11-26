"""Migration practice: every rule in docs/architecture.md ("Migrations") is held by a test here."""

import asyncio
import re
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, MetaData, Table, Text, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.schema import CreateIndex, CreateTable

from code_factory.platform.config import Settings
from code_factory.platform.db import EXPECTED_REVISION, Base, check_database
from code_factory.platform.db import migrate as migrate_module
from code_factory.platform.db.migrate import alembic_config, create_migration_engine, upgrade
from repo_files import ROOT

SCHEMA_INFO_REVISION = "2fdc42b35fd5"  # the schema revision the seed revision follows
# Columns that are genuinely optional: absence is a fact (never revoked, never used), not a default.
NULLABLE = {
    ("broker_tokens", "connection"),  # null: the run uses no named connection
    ("broker_tokens", "cap_usd"),  # null: no spending cap
    ("broker_tokens", "run_key_id"),  # null until a run key is minted
    ("broker_tokens", "ended_at"),  # null while the run goes on
    ("broker_tokens", "key_state_at"),  # null until the key changes state
    ("broker_tokens", "delete_claimed_at"),  # null until a sweep claims the deletion
    ("broker_tokens", "key_delete_failed_at"),  # null unless a deletion failed
    ("broker_tokens", "key_delete_error"),  # null unless a deletion failed
    ("delivery_events", "retry_at"),  # null: the failure is final
    ("delivery_pulls", "additions"),  # null: GitHub gave no count, or read before it was kept
    ("delivery_pulls", "deletions"),  # null: as additions
    ("delivery_pulls", "changed_files"),  # null: as additions
    ("delivery_pulls", "created_on_host"),  # null: older pull reads have no host timestamp
    ("delivery_pulls", "updated_on_host"),  # null: as created_on_host
    ("delivery_pulls", "merged_on_host"),  # null: GitHub has not recorded a merge
    ("delivery_pulls", "first_review_at"),  # null: no submitted maintainer review is known
    ("eval_records", "pass_at_1"),  # null for a review record
    ("eval_records", "pass_k"),
    ("eval_records", "pass_at_k"),
    ("eval_records", "caught"),  # null for a build record
    ("eval_records", "false_findings"),
    ("eval_records", "failed"),
    ("eval_records", "tokens"),  # null: no run reported tokens
    ("eval_task_runs", "passed"),  # null for a clean run
    ("eval_task_runs", "blocking"),  # null for a build or escape run, or a failed clean run
    ("eval_judgements", "score"),  # null for an answer
    ("eval_judgements", "scorer"),  # null for a score
    ("eval_judgements", "answer"),
    ("eval_judge_days", "finished_at"),  # null while the judging runs
    ("auth_tokens", "run_id"),
    ("auth_tokens", "ticket_id"),
    ("auth_tokens", "stage"),
    ("auth_tokens", "repository"),
    ("auth_tokens", "revoked_at"),
    ("auth_tokens", "last_used_at"),
    ("talk_questions", "answered_at"),
    ("talk_questions", "withdrawn_at"),
    ("talk_posts", "line"),
    ("talk_posts", "delivered_at"),
    ("releases", "published_at"),
    ("releases", "tag_commit"),
    ("releases", "tagged_at"),
    ("session_events", "agent_id"),
    ("connections", "management_key_name"),
    ("agents", "connection_id"),
    ("agents", "max_tokens"),
    ("agents", "max_seconds"),
    ("agents", "input_price"),
    ("agents", "output_price"),
    ("agents", "max_daily_usd"),
    ("agents", "paused_at"),
    ("agents", "context"),
    ("agents", "context_at"),
    *(
        ("runs", column)
        for column in (
            "ticket_id",
            "pid",
            "pid_started_at",
            "awake_started_at",
            "exit_code",
            "ended_at",
            "settled_at",
            "cost",
            "tokens",
            "cache_read",
            "turns",
            "commits",
            "limited_until",
            "context_at",
            "memory_digest",
        )
    ),
    ("permission_requests", "run_id"),
    ("permission_requests", "kind"),
    ("permission_requests", "verdict"),
    ("permission_requests", "answered_at"),
    ("check_runs", "started_at"),
    ("check_runs", "finished_at"),
    ("check_runs", "exit_code"),
    ("check_runs", "verdict"),
    ("metrics_merges", "pull"),
    ("metrics_merges", "ticket_id"),
    ("metrics_branch_cuts", "cut_at"),
}

REVISION_FILE = re.compile(r"\d{8}_\d{4}_[0-9a-f]{12}_[a-z0-9_]+\.py")


@pytest.fixture
def scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def test_history_is_one_line_ending_at_the_revision_the_app_expects(
    scripts: ScriptDirectory,
) -> None:
    assert scripts.get_heads() == [EXPECTED_REVISION]
    assert all(
        isinstance(revision.down_revision, str | None) for revision in scripts.walk_revisions()
    )


def test_every_revision_has_a_downgrade_and_a_readable_sortable_file_name(
    scripts: ScriptDirectory,
) -> None:
    for revision in scripts.walk_revisions():
        assert revision.module.downgrade is not None
        assert revision.path is not None
        assert REVISION_FILE.fullmatch(Path(revision.path).name), revision.path


async def test_the_models_and_the_migrations_agree(connection: AsyncConnection) -> None:
    def differences(sync_connection: object) -> list[object]:
        context = MigrationContext.configure(
            sync_connection,  # ty: ignore[invalid-argument-type]
            opts={"compare_type": True, "compare_server_default": True},
        )
        return list(compare_metadata(context, Base.metadata))

    assert await connection.run_sync(differences) == []


def test_upgrade_downgrade_upgrade_ends_at_head_with_the_seed_row(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    state = asyncio.run(check_database(settings))
    assert (state.revision, state.data_format) == (EXPECTED_REVISION, 1)


def test_downgrading_the_data_revision_removes_the_seed_row_and_upgrading_restores_it(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    config = alembic_config()
    command.downgrade(
        config, SCHEMA_INFO_REVISION
    )  # the revision before the seed, whatever follows
    assert asyncio.run(_scalar(settings, "select count(*) from schema_info")) == 0
    command.upgrade(config, "head")
    assert asyncio.run(_scalar(settings, "select data_format_version from schema_info")) == 1


def test_upgrade_on_a_database_at_head_changes_nothing(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    upgrade()
    assert asyncio.run(check_database(settings)).revision == EXPECTED_REVISION


async def test_constraints_have_the_names_the_convention_derives(
    db_session: AsyncSession,
) -> None:
    rows = await db_session.execute(
        text(
            "select conname from pg_constraint "
            # Postgres 18+ lists NOT NULL as contype 'n' and names it itself; ours are the rest.
            "where conrelid = 'schema_info'::regclass and contype in ('p', 'f', 'u', 'c') "
            "order by conname"
        )
    )
    assert [row[0] for row in rows] == ["ck_schema_info_single_row", "pk_schema_info"]


async def test_schema_info_holds_one_row_and_names_the_constraint_that_says_so(
    db_session: AsyncSession,
) -> None:
    savepoint = db_session.begin_nested()
    statement = text("insert into schema_info (id, data_format_version) values (2, 1)")
    with pytest.raises(IntegrityError, match="ck_schema_info_single_row"):
        async with savepoint:
            await db_session.execute(statement)
    savepoint = db_session.begin_nested()
    statement = text("insert into schema_info (id, data_format_version) values (1, 1)")
    with pytest.raises(IntegrityError, match="pk_schema_info"):
        async with savepoint:
            await db_session.execute(statement)


async def test_columns_use_the_postgres_types_the_rules_ask_for(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "select table_name, column_name, data_type, character_maximum_length, is_nullable "
                "from information_schema.columns "
                "where table_schema = current_schema() and table_name <> 'alembic_version'"
            )
        )
    ).all()
    assert rows
    for table, column, data_type, max_length, nullable in rows:
        where = f"{table}.{column}"
        assert data_type != "timestamp without time zone", f"{where}: use timestamptz"
        assert max_length is None, f"{where}: use text unless there is a real limit"
        assert nullable == "NO" or (table, column) in NULLABLE, f"{where}: NOT NULL by default"
    updated_at = next(row for row in rows if row[:2] == ("schema_info", "updated_at"))
    assert updated_at[2] == "timestamp with time zone"


async def test_every_foreign_key_column_is_indexed(db_session: AsyncSession) -> None:
    unindexed = (
        await db_session.execute(
            text(
                """
                select c.conrelid::regclass::text, c.conname
                from pg_constraint c
                where c.contype = 'f'
                  and not exists (
                    select 1 from pg_index i
                    where i.indrelid = c.conrelid
                      and (i.indkey::int2[])[0:cardinality(c.conkey) - 1] @> c.conkey
                  )
                """
            )
        )
    ).all()
    assert unindexed == []


async def test_migration_sessions_fail_fast_on_locks_and_long_statements(
    settings: Settings,
    migrated: None,  # noqa: ARG001
) -> None:
    engine = create_migration_engine(settings)
    try:
        async with engine.connect() as connection:
            lock = (await connection.execute(text("show lock_timeout"))).scalar_one()
            statement = (await connection.execute(text("show statement_timeout"))).scalar_one()
    finally:
        await engine.dispose()
    assert (lock, statement) == ("5s", "5min")


# --- Probe migrations: a throwaway script directory run through this repository's env.py ---

PROBE_REVISION = '''"""{message}"""

import sqlalchemy as sa
from alembic import op

revision = "{rev}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade() -> None:
{upgrade}


def downgrade() -> None:
    pass
'''


@pytest.fixture
def probe(tmp_path: Path, settings: Settings, migrated: None) -> Iterator[Config]:  # noqa: ARG001
    """An Alembic config with an empty script directory and its own version table."""
    (tmp_path / "versions").mkdir()
    shutil.copy(ROOT / "alembic" / "env.py", tmp_path / "env.py")
    shutil.copy(ROOT / "alembic" / "script.py.mako", tmp_path / "script.py.mako")
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    config.set_main_option("version_table", "alembic_version_probe")
    yield config
    asyncio.run(_drop_probe_objects(settings))


async def _drop_probe_objects(settings: Settings) -> None:
    engine = create_migration_engine(settings)
    try:
        async with engine.begin() as connection:
            for name in ("probe_a", "probe_b", "alembic_version_probe"):
                await connection.execute(text(f"drop table if exists {name}"))
    finally:
        await engine.dispose()


def _write_probe(config: Config, rev: str, down: str | None, upgrade_body: str) -> None:
    directory = Path(config.get_main_option("script_location") or "")
    source = PROBE_REVISION.format(
        message=rev,
        rev=rev,
        down=repr(down),
        upgrade="\n".join("    " + line for line in upgrade_body.splitlines()),
    )
    (directory / "versions" / f"{rev}.py").write_text(source, encoding="utf-8")


async def _scalar(settings: Settings, sql: str) -> object:
    engine = create_migration_engine(settings)
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(sql))).scalar_one_or_none()
    finally:
        await engine.dispose()


def test_each_migration_is_its_own_transaction(probe: Config, settings: Settings) -> None:
    _write_probe(probe, "p1", None, 'op.create_table("probe_a", sa.Column("id", sa.Integer()))')
    _write_probe(
        probe,
        "p2",
        "p1",
        'op.create_table("probe_b", sa.Column("id", sa.Integer()))\nraise RuntimeError("p2 fails")',
    )
    with pytest.raises(RuntimeError, match="p2 fails"):
        command.upgrade(probe, "head")
    # p1 committed on its own; p2 left nothing behind, neither its table nor a version row.
    assert asyncio.run(_scalar(settings, "select to_regclass('probe_a') is not null")) is True
    assert asyncio.run(_scalar(settings, "select to_regclass('probe_b') is not null")) is False
    assert asyncio.run(_scalar(settings, "select version_num from alembic_version_probe")) == "p1"


def test_a_concurrent_index_build_runs_in_an_autocommit_block(
    probe: Config, settings: Settings
) -> None:
    _write_probe(probe, "p1", None, 'op.create_table("probe_a", sa.Column("id", sa.Integer()))')
    _write_probe(
        probe,
        "p2",
        "p1",
        "with op.get_context().autocommit_block():\n"
        '    op.execute("CREATE INDEX CONCURRENTLY ix_probe_a_id ON probe_a (id)")',
    )
    command.upgrade(probe, "head")
    index = asyncio.run(
        _scalar(
            settings,
            "select indexname from pg_indexes "
            "where schemaname = current_schema() and tablename = 'probe_a'",
        )
    )
    assert index == "ix_probe_a_id"


def test_the_naming_convention_derives_a_deterministic_name_for_every_constraint_kind() -> None:
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)
    parent = Table("parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", ForeignKey("parent.id", ondelete="CASCADE"), index=True),
        Column("slug", Text, unique=True),
        Column("size", Integer),
        CheckConstraint("size > 0", name="positive"),
    )
    ddl = "".join(
        str(CreateTable(table)) + "".join(str(CreateIndex(i)) for i in table.indexes)
        for table in (parent, child)
    )
    for name in (
        "pk_parent",
        "pk_child",
        "fk_child_parent_id_parent",
        "uq_child_slug",
        "ix_child_parent_id",
        "ck_child_positive",
    ):
        assert name in ddl


def test_env_py_builds_its_engine_through_the_migration_engine_factory(
    settings: Settings,  # noqa: ARG001
    migrated: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[AsyncEngine] = []

    def recording_factory(given: Settings) -> AsyncEngine:
        engine = create_migration_engine(given)
        built.append(engine)
        return engine

    monkeypatch.setattr(migrate_module, "create_migration_engine", recording_factory)
    command.upgrade(alembic_config(), "head")
    assert len(built) == 1

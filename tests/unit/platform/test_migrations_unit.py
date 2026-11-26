"""Migration practice: every rule in docs/architecture.md ("Migrations") is held by a test here."""

import re
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, MetaData, Table, Text
from sqlalchemy.schema import CreateIndex, CreateTable

from code_factory.platform.db import EXPECTED_REVISION, Base
from code_factory.platform.db.migrate import alembic_config

# Columns that are genuinely optional: absence is a fact (never revoked, never used), not a default.

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


# --- Probe migrations: a throwaway script directory run through this repository's env.py ---


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

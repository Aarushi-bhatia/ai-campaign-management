"""Names, document links, facts, conflicts, corrections and the brand summary

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _brand_fk() -> sa.ForeignKey:
    return sa.ForeignKey("brands.id", ondelete="CASCADE")


def upgrade() -> None:
    for column in (
        sa.Column("phase", sa.String(40), nullable=False, server_default=""),
        sa.Column("phase_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("phase_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("names_hash", sa.String(64)),
        sa.Column("links_hash", sa.String(64)),
        sa.Column("checked_groups", JSONB, nullable=False, server_default="{}"),
        sa.Column("summary", sa.Text),
        sa.Column("summary_source_hash", sa.String(64)),
        sa.Column("summary_edited", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("summary_stale", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("summary_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
    ):
        op.add_column("brands", column)

    for column in (
        sa.Column("facts_sha256", sa.String(64)),
        sa.Column("facts_version", sa.Integer),
        sa.Column("facts_error", sa.Text),
        sa.Column("facts_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20)),
        sa.Column("status_reason", sa.Text),
        sa.Column("replaced_by_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="SET NULL")),
        sa.Column("doc_type", sa.String(30)),
    ):
        op.add_column("brand_files", column)

    op.create_table(
        "entities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, _brand_fk(), nullable=False, index=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("short_forms", JSONB, nullable=False),
        sa.Column("old_names", JSONB, nullable=False),
    )
    op.create_table(
        "doc_links",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, _brand_fk(), nullable=False, index=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("effect", sa.String(30), nullable=False),
        sa.Column("claim", sa.Text, nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
    )
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, _brand_fk(), nullable=False, index=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("subject_key", sa.String(300), nullable=False, index=True),
        sa.Column("attribute", sa.String(300), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(300), nullable=False),
        sa.Column("evidence", sa.Text, nullable=False),
    )
    op.create_table(
        "conflicts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, _brand_fk(), nullable=False, index=True),
        sa.Column("subject_key", sa.String(300), nullable=False, index=True),
        sa.Column("group_hash", sa.String(64), nullable=False),
        sa.Column("point", sa.Text, nullable=False),
        sa.Column("topic", sa.String(300), nullable=False),
        sa.Column("fact_ids", JSONB, nullable=False),
        sa.Column("owner_file_ids", JSONB, nullable=False),
        sa.Column("winner_file_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="SET NULL")),
        sa.Column("rule", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "brand_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, _brand_fk(), nullable=False, index=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("target", sa.String(1000), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("brand_decisions", "conflicts", "facts", "doc_links", "entities"):
        op.drop_table(table)
    for column in ("facts_sha256", "facts_version", "facts_error", "facts_call_id", "status", "status_reason",
                   "replaced_by_id", "doc_type"):
        op.drop_column("brand_files", column)
    for column in ("phase", "phase_done", "phase_total", "names_hash", "links_hash", "checked_groups", "summary",
                   "summary_source_hash", "summary_edited", "summary_stale", "summary_call_id"):
        op.drop_column("brands", column)

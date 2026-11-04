"""Brands, their files and document sections with search vectors

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("documents_total", sa.Integer, nullable=False),
        sa.Column("documents_done", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("reviewed", sa.Boolean, nullable=False),
        sa.Column("read_finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "brand_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("text", sa.Text),
        sa.Column("basics", JSONB),
        sa.Column("sections_sha256", sa.String(64)),
        sa.Column("card", JSONB),
        sa.Column("card_sha256", sa.String(64)),
        sa.Column("card_version", sa.Integer),
        sa.Column("card_error", sa.Text),
        sa.Column("card_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("brand_id", "path"),
    )
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("heading", sa.String(1000), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("tokens", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(1536)),
    )
    op.add_column(
        "ai_calls",
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="SET NULL"), index=True),
    )


def downgrade() -> None:
    op.drop_column("ai_calls", "brand_id")
    op.drop_table("sections")
    op.drop_table("brand_files")
    op.drop_table("brands")

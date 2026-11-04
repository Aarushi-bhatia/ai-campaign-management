"""Image info, restriction fields and per-channel image rules

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_info",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("file_id", sa.Integer, sa.ForeignKey("brand_files.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("record", JSONB, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("description_source", sa.String(20), nullable=False),
        sa.Column("image_type", sa.String(40), nullable=False),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("transparent", sa.Boolean, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("describe_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("notes", JSONB),
        sa.Column("notes_hash", sa.String(64)),
        sa.Column("notes_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
    )
    op.add_column("brands", sa.Column("image_rules", JSONB))
    op.add_column("brands", sa.Column("image_rules_hash", sa.String(64)))
    op.add_column(
        "brands", sa.Column("image_rules_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL"))
    )


def downgrade() -> None:
    for column in ("image_rules_call_id", "image_rules_hash", "image_rules"):
        op.drop_column("brands", column)
    op.drop_table("image_info")

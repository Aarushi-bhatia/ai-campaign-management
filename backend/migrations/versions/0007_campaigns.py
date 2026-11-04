"""Campaigns, and typed chat messages (question cards, notes, plans)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("brief", sa.Text, nullable=False),
        sa.Column("questions", JSONB, nullable=False),
        sa.Column("brief_rules", JSONB, nullable=False),
        sa.Column("assumptions", JSONB, nullable=False),
        sa.Column("plan", JSONB),
        sa.Column("plan_version", sa.Integer, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("noted_conflicts", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("messages", sa.Column("kind", sa.String(20), nullable=False, server_default="text"))
    op.add_column("messages", sa.Column("data", JSONB))


def downgrade() -> None:
    op.drop_column("messages", "data")
    op.drop_column("messages", "kind")
    op.drop_table("campaigns")

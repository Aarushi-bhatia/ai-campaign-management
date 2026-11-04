"""Research findings, written assets and their versions, memory, and the brand's writing rules

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, default in (("research", "[]"), ("searches", "[]"), ("memories_used", "[]"), ("hand_fixes", "{}")):
        op.add_column("campaigns", sa.Column(name, JSONB, nullable=False, server_default=default))
    op.add_column("campaigns", sa.Column("memory_checked_upto", sa.Integer, nullable=False, server_default="0"))
    op.add_column("brands", sa.Column("writing_rules", JSONB))
    op.add_column("brands", sa.Column("writing_rules_hash", sa.String(64)))
    op.add_column("brands", sa.Column("writing_rules_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")))
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("plan_id", sa.String(40), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("content", JSONB),
        sa.Column("image", JSONB),
        sa.Column("looked_up", JSONB, nullable=False),
        sa.Column("fixed", JSONB, nullable=False),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "asset_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("based_on", sa.Integer),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("image", JSONB),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("call_ids", JSONB, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("pinned", sa.Boolean, nullable=False),
        sa.Column("source_chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "campaign_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="SET NULL"), unique=True),
        sa.Column("chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="SET NULL")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("goal", sa.Text, nullable=False),
        sa.Column("audience", sa.Text, nullable=False),
        sa.Column("angle", sa.Text, nullable=False),
        sa.Column("assets", JSONB, nullable=False),
        sa.Column("images", JSONB, nullable=False),
        sa.Column("dates", sa.Text, nullable=False),
        sa.Column("extra", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("campaign_records")
    op.drop_table("memory_items")
    op.drop_table("asset_versions")
    op.drop_table("assets")
    for name in ("writing_rules_call_id", "writing_rules_hash", "writing_rules"):
        op.drop_column("brands", name)
    for name in ("research", "searches", "memories_used", "hand_fixes", "memory_checked_upto"):
        op.drop_column("campaigns", name)

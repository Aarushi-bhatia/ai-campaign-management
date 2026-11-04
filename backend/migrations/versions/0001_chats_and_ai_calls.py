"""Chats, messages and the AI call log

Revision ID: 0001
Revises:
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("step", sa.String(200), nullable=False),
        sa.Column("size", sa.String(20), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="SET NULL"), index=True),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_cached", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("request", JSONB, nullable=False),
        sa.Column("response_text", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chat_id", sa.Integer, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("ai_call_id", sa.Integer, sa.ForeignKey("ai_calls.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("ai_calls")
    op.drop_table("chats")

"""Conflicts record the sides taken, so documents that agree don't compete

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conflicts", sa.Column("sides", JSONB, nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("conflicts", "sides")

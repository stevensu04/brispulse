"""feed fetch log

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16 12:49:43.308593
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feed_fetch",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("feed", sa.String(length=24), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("body_bytes", sa.Integer(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=True),
        sa.Column("accepted_count", sa.Integer(), nullable=True),
        sa.Column("rejected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("anomaly", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("static_version_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_fetch")),
    )
    op.create_index(
        "ix_feed_fetch_feed_fetched_at", "feed_fetch", ["feed", "fetched_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_feed_fetch_feed_fetched_at", table_name="feed_fetch")
    op.drop_table("feed_fetch")

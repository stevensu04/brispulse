"""static gtfs reference tables

Revision ID: 0001
Revises: -
Create Date: 2026-11-16 12:20:52.418947
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "static_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feed_publisher", sa.Text(), nullable=True),
        sa.Column("feed_start_date", sa.Date(), nullable=True),
        sa.Column("feed_end_date", sa.Date(), nullable=True),
        sa.Column("route_count", sa.Integer(), nullable=False),
        sa.Column("stop_count", sa.Integer(), nullable=False),
        sa.Column("trip_count", sa.Integer(), nullable=False),
        sa.Column("stop_time_rows", sa.Integer(), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_static_version")),
    )
    op.create_index(
        "uq_static_version_one_active",
        "static_version",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "route",
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("long_name", sa.Text(), nullable=True),
        sa.Column("route_type", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("color", sa.String(length=6), nullable=True),
        sa.Column("text_color", sa.String(length=6), nullable=True),
        sa.ForeignKeyConstraint(
            ["static_version_id"],
            ["static_version.id"],
            name=op.f("fk_route_static_version_id_static_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("static_version_id", "route_id", name=op.f("pk_route")),
    )
    op.create_table(
        "service_calendar",
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("monday", sa.Boolean(), nullable=False),
        sa.Column("tuesday", sa.Boolean(), nullable=False),
        sa.Column("wednesday", sa.Boolean(), nullable=False),
        sa.Column("thursday", sa.Boolean(), nullable=False),
        sa.Column("friday", sa.Boolean(), nullable=False),
        sa.Column("saturday", sa.Boolean(), nullable=False),
        sa.Column("sunday", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["static_version_id"],
            ["static_version.id"],
            name=op.f("fk_service_calendar_static_version_id_static_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "static_version_id", "service_id", name=op.f("pk_service_calendar")
        ),
    )
    op.create_table(
        "service_calendar_date",
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("exception_type", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["static_version_id"],
            ["static_version.id"],
            name=op.f("fk_service_calendar_date_static_version_id_static_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "static_version_id", "service_id", "date", name=op.f("pk_service_calendar_date")
        ),
    )
    op.create_table(
        "stop",
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("stop_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("location_type", sa.SmallInteger(), nullable=False),
        sa.Column("parent_station", sa.Text(), nullable=True),
        sa.Column("platform_code", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["static_version_id"],
            ["static_version.id"],
            name=op.f("fk_stop_static_version_id_static_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("static_version_id", "stop_id", name=op.f("pk_stop")),
    )
    op.create_table(
        "trip",
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("headsign", sa.Text(), nullable=True),
        sa.Column("direction_id", sa.SmallInteger(), nullable=True),
        sa.Column("shape_id", sa.Text(), nullable=True),
        sa.Column("first_departure_s", sa.Integer(), nullable=False),
        sa.Column("last_arrival_s", sa.Integer(), nullable=False),
        sa.Column("stop_count", sa.Integer(), nullable=False),
        sa.Column("first_stop_id", sa.Text(), nullable=False),
        sa.Column("last_stop_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["static_version_id"],
            ["static_version.id"],
            name=op.f("fk_trip_static_version_id_static_version"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("static_version_id", "trip_id", name=op.f("pk_trip")),
    )
    op.create_index(
        "ix_trip_version_route", "trip", ["static_version_id", "route_id"], unique=False
    )
    op.create_index(
        "ix_trip_version_service", "trip", ["static_version_id", "service_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trip_version_service", table_name="trip")
    op.drop_index("ix_trip_version_route", table_name="trip")
    op.drop_table("trip")
    op.drop_table("stop")
    op.drop_table("service_calendar_date")
    op.drop_table("service_calendar")
    op.drop_table("route")
    op.drop_index(
        "uq_static_version_one_active",
        table_name="static_version",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("static_version")

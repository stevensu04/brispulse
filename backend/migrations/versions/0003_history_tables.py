"""history tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16 17:41:45.306310
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_record",
        sa.Column("alert_id", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cause", sa.String(length=32), nullable=False),
        sa.Column("effect", sa.String(length=32), nullable=False),
        sa.Column("header", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("active_periods", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("route_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stop_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("alert_id", "content_hash", name=op.f("pk_alert_record")),
    )
    op.create_index("ix_alert_record_last_seen", "alert_record", ["last_seen_at"], unique=False)
    op.create_table(
        "network_sample",
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("static_version_id", sa.Integer(), nullable=True),
        sa.Column("vehicle_positions_state", sa.String(length=16), nullable=False),
        sa.Column("trip_updates_state", sa.String(length=16), nullable=False),
        sa.Column("alerts_state", sa.String(length=16), nullable=False),
        sa.Column("vehicles_fresh", sa.Integer(), nullable=True),
        sa.Column("vehicles_last_seen", sa.Integer(), nullable=True),
        sa.Column("trips_running", sa.Integer(), nullable=True),
        sa.Column("trips_scheduled", sa.Integer(), nullable=True),
        sa.Column("trips_with_update", sa.Integer(), nullable=True),
        sa.Column("trips_with_vehicle", sa.Integer(), nullable=True),
        sa.Column("delay_sample_size", sa.Integer(), nullable=True),
        sa.Column("delay_median_s", sa.Integer(), nullable=True),
        sa.Column("delay_p90_s", sa.Integer(), nullable=True),
        sa.Column("delay_early", sa.Integer(), nullable=True),
        sa.Column("delay_within_band", sa.Integer(), nullable=True),
        sa.Column("delay_late", sa.Integer(), nullable=True),
        sa.Column("delay_excluded_implausible", sa.Integer(), nullable=True),
        sa.Column("alerts_active", sa.Integer(), nullable=True),
        sa.Column("alerts_active_planned_works", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("sampled_at", "mode", name=op.f("pk_network_sample")),
    )
    op.create_table(
        "route_day_stats",
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=True),
        sa.Column("trips_observed", sa.Integer(), nullable=False),
        sa.Column("trips_scheduled", sa.Integer(), nullable=True),
        sa.Column("delay_p50_s", sa.Integer(), nullable=True),
        sa.Column("delay_p90_s", sa.Integer(), nullable=True),
        sa.Column("trips_early", sa.Integer(), nullable=False),
        sa.Column("trips_within_band", sa.Integer(), nullable=False),
        sa.Column("trips_late", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("service_date", "route_id", name=op.f("pk_route_day_stats")),
    )
    op.create_table(
        "trip_record",
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("trip_id", sa.Text(), nullable=False),
        sa.Column("route_id", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=True),
        sa.Column("relationship", sa.String(length=24), nullable=False),
        sa.Column("vehicle_id", sa.Text(), nullable=True),
        sa.Column("static_version_id", sa.Integer(), nullable=False),
        sa.Column("first_obs_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_obs_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("obs_count", sa.Integer(), nullable=False),
        sa.Column("delay_median_s", sa.Integer(), nullable=True),
        sa.Column("delay_min_s", sa.Integer(), nullable=True),
        sa.Column("delay_max_s", sa.Integer(), nullable=True),
        sa.Column("delay_last_s", sa.Integer(), nullable=True),
        sa.Column("early_obs_count", sa.Integer(), nullable=False),
        sa.Column("late_obs_count", sa.Integer(), nullable=False),
        sa.Column("implausible_count", sa.Integer(), nullable=False),
        sa.Column("without_delay_count", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("samples", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.PrimaryKeyConstraint("service_date", "trip_id", name=op.f("pk_trip_record")),
    )
    op.create_index(
        "ix_trip_record_date_route", "trip_record", ["service_date", "route_id"], unique=False
    )
    op.create_index(
        "ix_trip_record_in_flight",
        "trip_record",
        ["completed"],
        unique=False,
        postgresql_where=sa.text("NOT completed"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trip_record_in_flight",
        table_name="trip_record",
        postgresql_where=sa.text("NOT completed"),
    )
    op.drop_index("ix_trip_record_date_route", table_name="trip_record")
    op.drop_table("trip_record")
    op.drop_table("route_day_stats")
    op.drop_table("network_sample")
    op.drop_index("ix_alert_record_last_seen", table_name="alert_record")
    op.drop_table("alert_record")

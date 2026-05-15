"""drop standalone cars table; add vendor_cars

Revision ID: 0003_vendor_cars
Revises: 0002_scan_events
Create Date: 2026-05-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_vendor_cars"
down_revision: Union[str, None] = "0002_scan_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cars")

    op.create_table(
        "vendor_cars",
        sa.Column(
            "car_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("car_name", sa.String(255), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("km_driven", sa.Integer, nullable=False),
        sa.Column("cost_lakh", sa.Numeric(8, 2), nullable=False),
        sa.Column("registration_year", sa.Integer, nullable=False),
        sa.Column("transmission", sa.String(20), nullable=False),
        sa.Column("fuel_type", sa.String(20), nullable=False),
        sa.Column("owner_type", sa.String(20), nullable=False),
        # SHA-256 hex of vendor_id + normalized field values; used as the
        # uniqueness key so duplicate uploads (within a file or across runs)
        # are rejected by the DB rather than relying on app-side checks.
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("vendor_id", "row_hash", name="uq_vendor_cars_vendor_row"),
    )
    op.create_index("ix_vendor_cars_vendor_id", "vendor_cars", ["vendor_id"])
    op.create_index("ix_vendor_cars_created_at", "vendor_cars", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_vendor_cars_created_at", table_name="vendor_cars")
    op.drop_index("ix_vendor_cars_vendor_id", table_name="vendor_cars")
    op.drop_table("vendor_cars")

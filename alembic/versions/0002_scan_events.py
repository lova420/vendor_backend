"""scan_events table for QR-scan tracking

Revision ID: 0002_scan_events
Revises: 0001_initial
Create Date: 2026-05-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_scan_events"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scan_events",
        sa.Column(
            "id",
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
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_scan_events_vendor_created",
        "scan_events",
        ["vendor_id", "created_at"],
    )
    op.create_index("ix_scan_events_created_at", "scan_events", ["created_at"])
    op.create_index(
        "ix_scan_events_vendor_ip",
        "scan_events",
        ["vendor_id", "ip_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_events_vendor_ip", table_name="scan_events")
    op.drop_index("ix_scan_events_created_at", table_name="scan_events")
    op.drop_index("ix_scan_events_vendor_created", table_name="scan_events")
    op.drop_table("scan_events")

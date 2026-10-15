"""Add date-only deadlines to events.

Revision ID: 0002_add_due_date
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_due_date"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("due_date", sa.String(length=10), nullable=True))
    op.create_index("ix_events_due_date", "events", ["due_date"])
    op.execute(
        "UPDATE events SET due_date = substr(due_at, 1, 10) "
        "WHERE due_at IS NOT NULL AND type IN ('task', 'reminder')"
    )


def downgrade() -> None:
    op.drop_index("ix_events_due_date", table_name="events")
    op.drop_column("events", "due_date")

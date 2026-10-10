"""Initial events and dialogue sessions tables."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=100), nullable=True, unique=True),
        sa.Column("owner_session_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.String(length=40), nullable=True),
        sa.Column("ends_at", sa.String(length=40), nullable=True),
        sa.Column("due_at", sa.String(length=40), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("raw_user_text", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_events_owner_session_id", "events", ["owner_session_id"])
    op.create_index("ix_events_source", "events", ["source"])
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_starts_at", "events", ["starts_at"])
    op.create_index("ix_events_due_at", "events", ["due_at"])
    op.create_index("ix_events_search_text", "events", ["search_text"])
    op.create_table(
        "dialogue_sessions",
        sa.Column("session_id", sa.String(length=36), primary_key=True),
        sa.Column("pending_action", sa.Text(), nullable=True),
        sa.Column("last_referenced_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["last_referenced_event_id"], ["events.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("dialogue_sessions")
    op.drop_index("ix_events_search_text", table_name="events")
    op.drop_index("ix_events_due_at", table_name="events")
    op.drop_index("ix_events_starts_at", table_name="events")
    op.drop_index("ix_events_type", table_name="events")
    op.drop_index("ix_events_source", table_name="events")
    op.drop_index("ix_events_owner_session_id", table_name="events")
    op.drop_table("events")

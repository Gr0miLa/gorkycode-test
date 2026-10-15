from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    owner_session_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[str | None] = mapped_column(String(40), index=True)
    ends_at: Mapped[str | None] = mapped_column(String(40))
    due_at: Mapped[str | None] = mapped_column(String(40), index=True)
    due_date: Mapped[str | None] = mapped_column(String(10), index=True)
    timezone: Mapped[str] = mapped_column(String(100), default="Europe/Moscow")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    raw_user_text: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    search_text: Mapped[str] = mapped_column(Text, default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DialogueSession(Base):
    __tablename__ = "dialogue_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pending_action: Mapped[str | None] = mapped_column(Text)
    last_referenced_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

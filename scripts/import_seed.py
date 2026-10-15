import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.db.base import Event
from app.db.session import SessionLocal, init_db
from app.services.text import extract_tags, normalize_text


MEETING_HINTS = ("встреч", "созвон", "демо", "обсуд", "интервью")
REMINDER_HINTS = ("напомнить", "не забыть")


def infer_type(text: str) -> str:
    normalized = normalize_text(text)
    if any(hint in normalized for hint in MEETING_HINTS):
        return "meeting"
    if any(hint in normalized for hint in REMINDER_HINTS):
        return "reminder"
    return "task"


def import_seed(path: Path) -> tuple[int, int]:
    init_db()
    created = skipped = 0
    timezone = get_settings().default_timezone
    with path.open(encoding="utf-8-sig", newline="") as source, SessionLocal() as db:
        for row in csv.DictReader(source):
            source_id = f"seed:{row['id']}"
            if db.scalar(select(Event.id).where(Event.source_id == source_id)):
                skipped += 1
                continue
            title = row["text"].strip()
            moment = datetime.fromisoformat(f"{row['date']}T{row['time']}:00").isoformat()
            event_type = infer_type(title)
            tags = extract_tags(title)
            event = Event(
                source_id=source_id,
                owner_session_id=None,
                source="seed",
                type=event_type,
                title=title,
                starts_at=moment if event_type == "meeting" else None,
                ends_at=None,
                due_at=moment if event_type != "meeting" else None,
                due_date=row["date"] if event_type != "meeting" else None,
                timezone=timezone,
                status="pending",
                raw_user_text=title,
                tags=json.dumps(tags, ensure_ascii=False),
                search_text=normalize_text(" ".join([title, *tags])),
            )
            db.add(event)
            created += 1
        db.commit()
    return created, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import example events into SQLite")
    parser.add_argument("path", nargs="?", default="voice_assistant_events_1000.csv")
    args = parser.parse_args()
    created, skipped = import_seed(Path(args.path))
    print(f"Imported: {created}; skipped: {skipped}")

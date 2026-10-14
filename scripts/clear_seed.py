from sqlalchemy import delete

from app.db.base import Event
from app.db.session import SessionLocal


with SessionLocal() as db:
    result = db.execute(delete(Event).where(Event.source == "seed"))
    db.commit()

print(f"Deleted seed events: {result.rowcount}")

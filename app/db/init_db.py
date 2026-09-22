import json
from datetime import date
from pathlib import Path
from sqlalchemy import select
from app.db.base import Base, engine, SessionLocal
from app.models.entities import CityKnowledge, Event

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

def init_db() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(CityKnowledge.id).limit(1)):
            for row in json.loads((DATA_DIR / "city_knowledge.json").read_text()):
                db.add(CityKnowledge(**row))
        if not db.scalar(select(Event.id).limit(1)):
            for row in json.loads((DATA_DIR / "events.json").read_text()):
                row["event_date"] = date.fromisoformat(row["event_date"])
                db.add(Event(**row))
        db.commit()

if __name__ == "__main__":
    init_db()

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal, engine
from app.models import Client, Matter, Task


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        print(f"database={settings.sqlalchemy_database_url}")
        print(f"dialect={engine.dialect.name}")
        print(f"clients={db.scalar(select(func.count(Client.id))) or 0}")
        print(f"matters={db.scalar(select(func.count(Matter.id))) or 0}")
        print(f"tasks={db.scalar(select(func.count(Task.id))) or 0}")
        latest = db.scalars(select(Matter).order_by(Matter.id.desc()).limit(10)).all()
        print("latest_matters=")
        for matter in latest:
            print(f"{matter.id}\t{matter.case_number}\t{matter.ministry_case_number or '-'}\t{matter.title}")


if __name__ == "__main__":
    main()

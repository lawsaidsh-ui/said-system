from __future__ import annotations

import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Client, CourtSession, Matter
from app.routes.helpers import find_similar_client


CASES = [
    {
        "case_number": "2026/1408/1",
        "client_name": "محمد بشير",
        "opponent_name": "الجودة الراقية للاتصالات والتجارة",
    },
    {
        "case_number": "2026/1408/2",
        "client_name": "غلام رباني",
        "opponent_name": "الجودة الراقية للاتصالات والتجارة",
    },
    {
        "case_number": "2026/1408/4",
        "client_name": "حافظ حسين مافيا",
        "opponent_name": "الجودة الراقية للاتصالات والتجارة",
    },
]

REGISTRATION_DATE = date(2026, 1, 1)
CASE_TYPE = "رواتب"
COURT_NAME = "المحكمة الابتدائية بالسيب"
COURT_LEVEL = "محكمة ابتدائية"
STATUS_TEXT = "محكوم"


def backup_database() -> Path | None:
    database_path = ROOT / "saeed_law.db"
    if not database_path.exists():
        return None
    backup_path = ROOT / f"saeed_law.backup-before-manual-cases-2026-1408-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(database_path, backup_path)
    return backup_path


def next_office_case_number(db) -> str:
    year = REGISTRATION_DATE.year
    sequence = (db.scalar(select(Matter.id).order_by(Matter.id.desc()).limit(1)) or 0) + 1
    while True:
        candidate = f"OFF-{year}-{sequence:04d}"
        exists = db.scalar(select(Matter.id).where(Matter.case_number == candidate))
        if not exists:
            return candidate
        sequence += 1


def ensure_client(db, name: str) -> Client:
    client = find_similar_client(db, name)
    if client:
        return client
    client = Client(full_name=name, client_type="individual")
    db.add(client)
    db.flush()
    return client


def ensure_completed_session(db, matter: Matter) -> None:
    session = db.scalar(select(CourtSession).where(CourtSession.matter_id == matter.id).limit(1))
    if not session:
        session = CourtSession(matter_id=matter.id, session_date=REGISTRATION_DATE, court_name=COURT_NAME)
        db.add(session)
    session.session_date = REGISTRATION_DATE
    session.court_name = COURT_NAME
    session.session_status = "completed"
    session.decision_summary = "محكوم حسب حالة الدعوى في بيانات المحكمة."
    session.next_action = "مراجعة منطوق الحكم وإدخال تفاصيله عند توفر نسخة الحكم."
    session.notes = "تم إدخالها يدويًا من جدول القضايا المرسل."


def main() -> None:
    backup_path = backup_database()
    if backup_path:
        print(f"backup={backup_path.name}")

    created = 0
    updated = 0
    with SessionLocal() as db:
        for item in CASES:
            client = ensure_client(db, item["client_name"])
            matter = db.scalar(select(Matter).where(Matter.ministry_case_number == item["case_number"]))
            if matter:
                updated += 1
            else:
                matter = Matter(
                    case_number=next_office_case_number(db),
                    ministry_case_number=item["case_number"],
                )
                db.add(matter)
                created += 1

            matter.title = f"{CASE_TYPE} - {item['case_number']}"
            matter.client_id = client.id
            matter.case_type = CASE_TYPE
            matter.court_name = COURT_NAME
            matter.court_level = COURT_LEVEL
            matter.opponent_name = item["opponent_name"]
            matter.status = "closed"
            matter.priority = "medium"
            matter.opened_at = REGISTRATION_DATE
            matter.closed_at = REGISTRATION_DATE
            matter.description = (
                f"رقم الدعوى: {item['case_number']}\n"
                f"تاريخ التسجيل: {REGISTRATION_DATE.isoformat()}\n"
                f"درجة التقاضي: {COURT_LEVEL}\n"
                f"الفئة: {CASE_TYPE}\n"
                f"المحكمة: {COURT_NAME}\n"
                f"حالة الدعوى: {STATUS_TEXT}\n"
                f"الطرف الأول: {item['client_name']}\n"
                f"الطرف الثاني: {item['opponent_name']}"
            )
            db.flush()
            ensure_completed_session(db, matter)

        db.commit()

    print(f"created={created}")
    print(f"updated={updated}")


if __name__ == "__main__":
    main()

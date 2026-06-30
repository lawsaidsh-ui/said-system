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
from app.models import Client, Matter
from app.routes.helpers import find_similar_client

CASES = [
    {
        "case_number": "2025/1205/9939",
        "client_name": "علي ناصر سيف الرواحي",
        "registration_date": date(2025, 12, 18),
    },
    {
        "case_number": "2025/1205/10120",
        "client_name": "عدنان ناصر سيف حمد الرواحي",
        "registration_date": date(2025, 12, 23),
    },
]

OPPONENT_NAME = "مؤسسة الخلوت الحديثة - تاجر فرد"
CASE_TYPE = "مسؤولية تقصيرية وعقدية"
COURT_NAME = "المحكمة الابتدائية بسمد الشأن"
COURT_LEVEL = "محكمة ابتدائية"
STATUS_TEXT = "أحيل إلى قسم المحفوظات"


def backup_database() -> Path | None:
    database_path = ROOT / "saeed_law.db"
    if not database_path.exists():
        return None
    backup_path = ROOT / f"saeed_law.backup-before-manual-cases-2025-1205-archived-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(database_path, backup_path)
    return backup_path


def next_office_case_number(db, opened_at: date) -> str:
    year = opened_at.year
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


def main() -> None:
    backup_path = backup_database()
    if backup_path:
        print(f"backup={backup_path.name}")

    created = 0
    updated = 0
    with SessionLocal() as db:
        for item in CASES:
            opened_at = item["registration_date"]
            client = ensure_client(db, item["client_name"])
            matter = db.scalar(select(Matter).where(Matter.ministry_case_number == item["case_number"]))
            if matter:
                updated += 1
            else:
                matter = Matter(
                    case_number=next_office_case_number(db, opened_at),
                    ministry_case_number=item["case_number"],
                )
                db.add(matter)
                created += 1

            matter.title = f"{CASE_TYPE} - {item['case_number']}"
            matter.client_id = client.id
            matter.case_type = CASE_TYPE
            matter.court_name = COURT_NAME
            matter.court_level = COURT_LEVEL
            matter.opponent_name = OPPONENT_NAME
            matter.status = "archived"
            matter.priority = "medium"
            matter.opened_at = opened_at
            matter.closed_at = opened_at
            matter.description = (
                f"رقم الدعوى: {item['case_number']}\n"
                f"تاريخ التسجيل: {opened_at.isoformat()}\n"
                f"درجة التقاضي: {COURT_LEVEL}\n"
                f"الفئة: {CASE_TYPE}\n"
                f"المحكمة: {COURT_NAME}\n"
                f"حالة الدعوى: {STATUS_TEXT}\n"
                f"الطرف الأول: {item['client_name']}\n"
                f"الطرف الثاني: {OPPONENT_NAME}"
            )
            db.flush()

        db.commit()

    print(f"created={created}")
    print(f"updated={updated}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import shutil
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Client, CourtSession, Matter


DB_PATH = ROOT / "saeed_law.db"


def normalize_text(value: str | None) -> str:
    value = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", value or "")
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    value = re.sub(r"[^\w\s\u0600-\u06ff]", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def client_key(value: str | None) -> str:
    stop_words = {"بن", "بنت", "ابن", "إبن", "ابنة"}
    return " ".join(word for word in normalize_text(value).split() if word not in stop_words)


def backup_database() -> Path | None:
    if not DB_PATH.exists():
        return None
    backup_path = ROOT / f"saeed_law.backup-before-import-missing-cases-json-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def first_party(parties: list[str] | None, case_number: str) -> str:
    for party in parties or []:
        if party and not normalize_text(party).startswith("محامي"):
            return party.strip()[:255]
    return f"عميل غير محدد - {case_number}"[:255]


def first_opponent(parties: list[str] | None) -> str | None:
    for party in parties or []:
        if party:
            return party.strip()[:255]
    return None


def is_company(name: str) -> bool:
    markers = ("شركة", "مؤسسة", "ش.م", "ذ.م", "بنك", "وزارة", "بلدية", "هيئة")
    return any(marker in name for marker in markers)


def status_from_text(value: str | None) -> str:
    text = normalize_text(value)
    if "محكوم" in text or "حكم" in text:
        return "closed"
    if "الجلسات" in text:
        return "court_session"
    if "المحفوظات" in text or "الملاحظات" in text:
        return "waiting"
    return "open"


def next_office_case_number(db, year: int) -> str:
    prefix = f"OFF-{year}-"
    max_sequence = 0
    for case_number in db.scalars(select(Matter.case_number).where(Matter.case_number.like(f"{prefix}%"))).all():
        match = re.match(rf"{re.escape(prefix)}(\d+)$", case_number or "")
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))
    sequence = max_sequence + 1
    while True:
        candidate = f"{prefix}{sequence:04d}"
        if not db.scalar(select(Matter.id).where(Matter.case_number == candidate)):
            return candidate
        sequence += 1


def ensure_client(db, clients_by_key: dict[str, Client], name: str) -> Client:
    key = client_key(name)
    existing = clients_by_key.get(key)
    if existing:
        return existing
    client = Client(
        full_name=name,
        client_type="company" if is_company(name) else "individual",
        company_name=name if is_company(name) else None,
        notes="مستورد من ملف cases_2026_without_yellow.json.",
    )
    db.add(client)
    db.flush()
    clients_by_key[key] = client
    return client


def description_for(item: dict) -> str:
    first_parties = "\n".join(f"- {party}" for party in item.get("first_parties") or []) or "-"
    second_parties = "\n".join(f"- {party}" for party in item.get("second_parties") or []) or "-"
    return "\n".join(
        [
            f"رقم الدعوى: {item.get('case_number') or '-'}",
            f"تاريخ التسجيل: {item.get('registration_date') or '-'}",
            f"درجة التقاضي: {item.get('litigation_degree') or '-'}",
            f"الفئة: {item.get('category') or '-'}",
            f"المحكمة: {item.get('court') or '-'}",
            f"حالة الدعوى: {item.get('case_status') or '-'}",
            f"الطرف الأول:\n{first_parties}",
            f"الطرف الثاني:\n{second_parties}",
            f"صفحة المصدر: {item.get('source_page') or '-'}",
        ]
    )


def ensure_session(db, matter: Matter, opened_at: date | None, status_text: str | None) -> None:
    if not opened_at or matter.status not in {"court_session", "closed"}:
        return
    if db.scalar(select(CourtSession.id).where(CourtSession.matter_id == matter.id).limit(1)):
        return
    db.add(
        CourtSession(
            matter_id=matter.id,
            session_date=opened_at,
            court_name=matter.court_name or "المحكمة",
            session_status="completed" if matter.status == "closed" else "scheduled",
            decision_summary="محكوم حسب حالة الدعوى في ملف المصدر." if matter.status == "closed" else None,
            next_action="متابعة ملف القضية حسب حالة الدعوى.",
            notes=f"تم إنشاؤها تلقائياً من حالة الدعوى: {status_text or '-'}",
        )
    )


def import_missing_cases(input_path: Path, *, apply: bool) -> dict[str, int | str]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", []) if isinstance(payload, dict) else payload
    backup_path = backup_database() if apply else None
    result: dict[str, int | str] = {
        "input_cases": len(cases),
        "created_clients": 0,
        "created_matters": 0,
        "skipped_existing": 0,
        "backup": str(backup_path or "not-created"),
    }
    with SessionLocal() as db:
        existing_ministry_numbers = {
            normalize_text(number)
            for number in db.scalars(select(Matter.ministry_case_number)).all()
            if number
        }
        existing_case_numbers = {
            normalize_text(number)
            for number in db.scalars(select(Matter.case_number)).all()
            if number
        }
        clients_by_key = {client_key(client.full_name): client for client in db.scalars(select(Client)).all()}
        initial_client_count = len(clients_by_key)

        for item in cases:
            real_case_number = (item.get("case_number") or "").strip()
            if not real_case_number:
                continue
            number_key = normalize_text(real_case_number)
            if number_key in existing_ministry_numbers or number_key in existing_case_numbers:
                result["skipped_existing"] = int(result["skipped_existing"]) + 1
                continue

            opened_at = parse_date(item.get("registration_date"))
            year = opened_at.year if opened_at else int(payload.get("year") or date.today().year)
            client_name = first_party(item.get("first_parties"), real_case_number)
            client = ensure_client(db, clients_by_key, client_name)
            matter = Matter(
                case_number=next_office_case_number(db, year),
                ministry_case_number=real_case_number,
                title=f"{item.get('category') or 'قضية'} - {real_case_number}",
                client_id=client.id,
                assigned_lawyer_id=None,
                case_type=item.get("category"),
                court_name=item.get("court"),
                court_level=item.get("litigation_degree"),
                opponent_name=first_opponent(item.get("second_parties")),
                status=status_from_text(item.get("case_status")),
                priority="medium",
                description=description_for(item),
                claim_amount=Decimal("0"),
                opened_at=opened_at,
                closed_at=opened_at if status_from_text(item.get("case_status")) == "closed" else None,
            )
            db.add(matter)
            db.flush()
            ensure_session(db, matter, opened_at, item.get("case_status"))
            existing_ministry_numbers.add(number_key)
            result["created_matters"] = int(result["created_matters"]) + 1

        result["created_clients"] = len(clients_by_key) - initial_client_count
        if apply:
            db.commit()
        else:
            db.rollback()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Import only missing cases from a JSON file.")
    parser.add_argument("input")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    args = parser.parse_args()
    result = import_missing_cases(Path(args.input), apply=args.apply)
    for key, value in result.items():
        print(f"{key}={value}")
    print(f"committed={'true' if args.apply else 'false'}")


if __name__ == "__main__":
    main()

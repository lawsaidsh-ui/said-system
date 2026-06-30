from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import PROJECT_ROOT, get_settings
from app.database import SessionLocal
from app.models import (
    AuditLog,
    CaseFee,
    Client,
    Consultation,
    CourtSession,
    Document,
    Expense,
    Installment,
    Invoice,
    Matter,
    Notification,
    Payment,
    PaymentVoucher,
    ReceiptVoucher,
    Task,
    User,
    WhatsAppLog,
)

OFFICE_LAWYERS = (
    "سعيد بن عبدالله بن سعيد بن راشد الشبيبي",
    "حسين بن سالم بن سعيد بن محمد الراشدي",
)

LEGAL_NOISE_WORDS = {
    "محكمة",
    "المحكمة",
    "دعاوي",
    "دعوى",
    "ابتدائية",
    "ابتدائي",
    "الإبتدائية",
    "الابتدائية",
    "استئناف",
    "الاستئناف",
    "الأستئناف",
    "قسم",
    "الجلسات",
    "المحفوظات",
    "الملاحظات",
    "النهائية",
    "أحيل",
    "إلى",
    "تمت",
    "المراجعة",
    "مع",
    "ملف",
    "آخر",
    "ضم",
    "إليه",
    "محكوم",
    "مدنية",
    "مدني",
    "عمالية",
    "عمالي",
    "شرعية",
    "شرعي",
    "جنحة",
    "مستأنفة",
    "منازعة",
    "التنفيذ",
    "التنفيذية",
    "مسؤولية",
    "تقصيرية",
    "وعقدية",
    "نقل",
    "ملكية",
    "قرض",
    "بيع",
    "الطلاق",
    "والتطليق",
    "النسب",
    "فسخ",
    "تظلم",
    "أوامر",
    "على",
    "عريضة",
    "إثبات",
    "ملك",
    "عقد",
    "العمل",
    "وآثاره",
    "إعسار",
    "الرجوع",
    "لبيت",
    "الزوجية",
    "ديات",
    "وأروش",
    "تعويض",
    "رواتب",
    "فردي",
    "أخرى",
}

PLACE_WORDS = {
    "بمسقط",
    "بالسيب",
    "بنزوى",
    "ببركاء",
    "بصلالة",
    "بالرستاق",
    "بالعامرات",
    "بالمضيبي",
    "بإبراء",
    "بابراء",
    "بإزكي",
    "بسمائل",
    "بسمد",
    "الشأن",
    "بالقابل",
    "بأدم",
}

COMPANY_MARKERS = (
    "شركة",
    "مؤسسة",
    "المؤسسة",
    "وزارة",
    "صندوق",
    "مستشفيات",
    "مشاريع",
    "للتجارة",
    "للهندسة",
    "للتأمين",
    "ش م",
    "ش.م",
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import real Supreme Judiciary Council cases into the local database.")
    parser.add_argument("input_files", nargs="+", type=Path, help="Path(s) to Supreme Judiciary Council PDF or JSON files.")
    parser.add_argument("--append", action="store_true", help="Keep existing clients and matters instead of replacing them.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a database backup before replacing data.")
    return parser.parse_args()


def database_file() -> Path | None:
    url = get_settings().sqlalchemy_database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    return Path(url.removeprefix(prefix))


def backup_database() -> Path | None:
    db_path = database_file()
    if not db_path or not db_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}.backup-before-real-cases-{stamp}{db_path.suffix}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("JSON file must contain a list under the 'cases' key.")
    return cases


def has_arabic_presentation_forms(value: str) -> bool:
    return any(0xFB50 <= ord(char) <= 0xFEFF for char in value)


def pdf_cell_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).replace("\uf0dc", "").replace("\uf06e", "")
    if has_arabic_presentation_forms(value):
        normalized = "\n".join(line[::-1] for line in normalized.splitlines())
    return normalize_space(normalized)


def match_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"[\u064b-\u065f\u0670ـ]", "", value)
    return re.sub(r"[^0-9A-Za-z\u0600-\u06FF]+", "", value)


def contains_office_lawyer(value: str) -> bool:
    key = match_key(value)
    return any(match_key(name) in key for name in OFFICE_LAWYERS)


def source_year_from_case_number(case_number: str) -> int | None:
    match = re.match(r"(20\d{2})/", case_number or "")
    return int(match.group(1)) if match else None


def parse_registration_date(value: str, case_number: str) -> date | None:
    value = normalize_space(value).replace(" ", "")
    year = source_year_from_case_number(case_number)
    match = re.search(r"(20\d{2})-?(\d{2})-(\d{2})", value)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
    else:
        match = re.search(r"(\d{2})-(\d{2})", value)
        if not match or not year:
            return None
        month = int(match.group(1))
        day = int(match.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def clean_party_name(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"\(?\s*محامي\s*:.*", "", value)
    value = re.sub(r"(?:^|\s)\d{1,2}\.\s*", " ", value)
    value = re.sub(r"[()،:؛.]+", " ", value)
    return normalize_space(value)[:255]


def party_name_for_lawyer(party_text: str, lawyer_name: str) -> str | None:
    pattern = r"\s+".join(re.escape(part) for part in lawyer_name.split())
    match = re.search(pattern, party_text)
    if not match:
        return None
    prefix = party_text[: match.start()]
    markers = list(re.finditer(r"(?:^|\s)\d{1,2}\.\s*", prefix))
    if markers:
        prefix = prefix[markers[-1].end() :]
    name = clean_party_name(prefix)
    return name or None


def first_party_name(party_text: str) -> str | None:
    value = re.split(r"(?:^|\s)\d{1,2}\.\s*", party_text, maxsplit=2)
    candidate = value[1] if len(value) > 1 else party_text
    return clean_party_name(candidate) or None


def matched_lawyer_name(row: dict[str, Any]) -> str | None:
    for name in OFFICE_LAWYERS:
        if contains_office_lawyer(row.get("party_one", "")) and match_key(name) in match_key(row.get("party_one", "")):
            return name
        if contains_office_lawyer(row.get("party_two", "")) and match_key(name) in match_key(row.get("party_two", "")):
            return name
    return None


def client_and_opponent_from_parties(row: dict[str, Any]) -> tuple[str, str | None, str | None]:
    party_one = row.get("party_one", "")
    party_two = row.get("party_two", "")
    for lawyer_name in OFFICE_LAWYERS:
        if match_key(lawyer_name) in match_key(party_one):
            client = party_name_for_lawyer(party_one, lawyer_name) or first_party_name(party_one)
            return client or f"عميل غير محدد - {row['case_number']}", first_party_name(party_two), lawyer_name
        if match_key(lawyer_name) in match_key(party_two):
            client = party_name_for_lawyer(party_two, lawyer_name) or first_party_name(party_two)
            return client or f"عميل غير محدد - {row['case_number']}", first_party_name(party_one), lawyer_name
    return f"عميل غير محدد - {row['case_number']}", first_party_name(party_two) or first_party_name(party_one), None


def load_pdf_cases(path: Path) -> list[dict[str, Any]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required to import Supreme Judiciary Council PDFs.") from exc

    cases: list[dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            table = page.extract_table()
            if not table:
                continue
            for raw_row in table[1:]:
                if not raw_row or len(raw_row) < 9:
                    continue
                row = {
                    "source_file": path.name,
                    "source_year": None,
                    "page": page_number,
                    "case_number": pdf_cell_text(raw_row[8]),
                    "registration_date": pdf_cell_text(raw_row[7]),
                    "litigation_degree": pdf_cell_text(raw_row[6]),
                    "case_category": pdf_cell_text(raw_row[5]),
                    "court_name": pdf_cell_text(raw_row[4]),
                    "status_text": pdf_cell_text(raw_row[3]),
                    "party_one": pdf_cell_text(raw_row[2]),
                    "party_two": pdf_cell_text(raw_row[1]),
                    "details": pdf_cell_text(raw_row[0]),
                }
                if not re.match(r"20\d{2}/\d+/\d+", row["case_number"]):
                    continue
                combined = " ".join(
                    [
                        row["party_one"],
                        row["party_two"],
                        row["status_text"],
                        row["case_category"],
                        row["court_name"],
                    ]
                )
                if not contains_office_lawyer(combined):
                    continue
                row["source_year"] = source_year_from_case_number(row["case_number"])
                cases.append(row)
    return cases


def load_input_cases(paths: list[Path]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        if resolved.suffix.lower() == ".pdf":
            cases.extend(load_pdf_cases(resolved))
        else:
            cases.extend(load_cases(resolved))
    deduped: dict[str, dict[str, Any]] = {}
    for item in cases:
        case_number = normalize_space(item.get("case_number", ""))
        if case_number:
            deduped[case_number] = item
    return list(deduped.values())


def registration_date(item: dict[str, Any]) -> date | None:
    if item.get("registration_date") and item.get("case_number"):
        parsed = parse_registration_date(str(item["registration_date"]), str(item["case_number"]))
        if parsed:
            return parsed
    value = item.get("registration_date")
    year = item.get("source_year")
    if not value or not year:
        return None
    try:
        return datetime.strptime(f"{year}-{value}", "%Y-%m-%d").date()
    except ValueError:
        return None


def detect_case_type(text: str) -> str:
    if "التنفيذ" in text or "منازعة" in text:
        return "تنفيذ"
    if any(term in text for term in ("عمالية", "عمالي", "عقد العمل", "رواتب")):
        return "عمالي"
    if any(term in text for term in ("جنحة", "ديات", "أروش")):
        return "جزائي"
    if any(term in text for term in ("طلاق", "تطليق", "النسب", "شرعي", "الزوجية")):
        return "أحوال شخصية"
    if any(term in text for term in ("نقل ملكية", "إثبات ملك", "تظلم", "إعسار", "أوامر")):
        return "مدني"
    return "مدني"


def case_type_from_item(item: dict[str, Any]) -> str:
    return detect_case_type(" ".join([item.get("case_category", ""), item.get("row_text", "")]))


def detect_status(item: dict[str, Any], text: str) -> str:
    status_text = item.get("status_text") or ""
    if item.get("status_detected") == "محكوم" or "محكوم" in status_text or " محكوم " in f" {text} ":
        return "closed"
    if "قسم الجلسات" in status_text or "قسم الجلسات" in text:
        return "court_session"
    if "قسم المحفوظات" in status_text or "قسم المحفوظات" in text or "الملاحظات النهائية" in text:
        return "waiting"
    return "open"


def detect_court_level(text: str) -> str:
    if "استئناف" in text or "الأستئناف" in text:
        return "استئناف"
    if "التنفيذ" in text:
        return "تنفيذ"
    return "ابتدائي"


def court_level_from_item(item: dict[str, Any]) -> str:
    degree = item.get("litigation_degree")
    if degree:
        return degree
    return detect_court_level(item.get("row_text", ""))


def detect_place(text: str) -> str:
    places = [
        "سمد الشأن",
        "مسقط",
        "السيب",
        "نزوى",
        "بركاء",
        "الرستاق",
        "صلالة",
        "العامرات",
        "المضيبي",
        "إبراء",
        "ابراء",
        "إزكي",
        "سمائل",
        "القابل",
        "أدم",
    ]
    for place in places:
        compact = place.replace(" ", r"\s+")
        if re.search(rf"ب(?:ال)?{compact}", text):
            return "إبراء" if place == "ابراء" else place
    return "مسقط"


def detect_court_name(text: str) -> str:
    place = detect_place(text)
    if "استئناف" in text or "الأستئناف" in text:
        return f"محكمة الاستئناف ب{place}"
    return f"المحكمة الابتدائية ب{place}"


def court_name_from_item(item: dict[str, Any]) -> str:
    court_name = normalize_space(item.get("court_name", ""))
    if court_name:
        return court_name
    return detect_court_name(item.get("row_text", ""))


def strip_noise(value: str) -> str:
    value = re.sub(r"\b\d{4}/\d+/\d+\b", " ", value)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}-\d{2}\b", " ", value)
    value = re.sub(r"[()،:؛.]", " ", value)
    words = []
    for word in normalize_space(value).split(" "):
        if not word or word in LEGAL_NOISE_WORDS or word in PLACE_WORDS:
            continue
        words.append(word)
    cleaned = normalize_space(" ".join(words))
    cleaned = re.sub(r"^(بن|بنت)\s+", "", cleaned)
    return cleaned


def candidate_before_lawyer(row_text: str, marker_start: int) -> str:
    before = row_text[:marker_start]
    matches = list(re.finditer(r"(?:^|\s)(\d{1,2})\.\s*", before))
    if matches:
        before = before[matches[-1].end() :]
    return strip_noise(before)


def extract_client_name(item: dict[str, Any]) -> str:
    if item.get("party_one") or item.get("party_two"):
        client_name, _, _ = client_and_opponent_from_parties(item)
        return client_name[:255]
    row_text = normalize_space(item.get("row_text", ""))
    candidates: list[str] = []
    for match in re.finditer(r"محامي\s*:", row_text):
        candidate = candidate_before_lawyer(row_text, match.start())
        if candidate:
            candidates.append(candidate)

    usable = [candidate for candidate in candidates if len(candidate) >= 5]
    if usable:
        return max(usable, key=len)[:255]
    case_number = item.get("case_number") or "بدون رقم"
    return f"عميل غير محدد - {case_number}"[:255]


def extract_opponent_name(item: dict[str, Any], client_name: str) -> str | None:
    if item.get("party_one") or item.get("party_two"):
        _, opponent_name, _ = client_and_opponent_from_parties(item)
        return opponent_name[:255] if opponent_name else None
    row_text = normalize_space(item.get("row_text", ""))
    segments = re.split(r"(?:^|\s)\d{1,2}\.\s*", row_text)
    candidates = []
    for segment in segments[1:]:
        candidate = strip_noise(segment.split("محامي", 1)[0])
        if candidate and candidate != client_name and len(candidate) >= 5:
            candidates.append(candidate)
    return candidates[0][:255] if candidates else None


def is_company(name: str) -> bool:
    return any(marker in name for marker in COMPANY_MARKERS)


def client_name_key(value: str) -> str:
    cleaned = match_key(value)
    words = [
        word
        for word in cleaned.split()
        if word not in {"بن", "بنت", "ابن", "إبن", "ابنة"}
    ]
    return normalize_space(" ".join(words))


def preferred_lawyer_id(db: Session, item: dict[str, Any]) -> int | None:
    matched_name = matched_lawyer_name(item)
    if matched_name:
        users = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(["admin", "lawyer"]))).all()
        matched_key = match_key(matched_name)
        for user in users:
            if match_key(user.full_name) == matched_key:
                return user.id
    matched_names = item.get("matched_names") or []
    wanted = {normalize_space(entry.get("name", "")) for entry in matched_names if isinstance(entry, dict)}
    if not wanted:
        return None
    users = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(["admin", "lawyer"]))).all()
    for user in users:
        if normalize_space(user.full_name) in wanted:
            return user.id
    return None


def ids_for(db: Session, model: Any) -> list[int]:
    return list(db.scalars(select(model.id)).all())


def delete_existing_client_matter_data(db: Session) -> None:
    client_ids = ids_for(db, Client)
    matter_ids = ids_for(db, Matter)
    invoice_ids = ids_for(db, Invoice)
    task_ids = ids_for(db, Task)
    case_fee_ids = ids_for(db, CaseFee)

    if task_ids:
        db.execute(delete(Notification).where(Notification.task_id.in_(task_ids)))
    if invoice_ids:
        db.execute(delete(Payment).where(Payment.invoice_id.in_(invoice_ids)))
    if case_fee_ids:
        db.execute(delete(Installment).where(Installment.case_fee_id.in_(case_fee_ids)))

    if client_ids or matter_ids or invoice_ids:
        if client_ids:
            db.execute(delete(ReceiptVoucher).where(ReceiptVoucher.client_id.in_(client_ids)))
            db.execute(delete(PaymentVoucher).where(PaymentVoucher.client_id.in_(client_ids)))
            db.execute(delete(Consultation).where(Consultation.client_id.in_(client_ids)))
            db.execute(delete(Document).where(Document.client_id.in_(client_ids)))
            db.execute(delete(Task).where(Task.client_id.in_(client_ids)))
            db.execute(delete(WhatsAppLog).where(WhatsAppLog.client_id.in_(client_ids)))
            db.execute(delete(Installment).where(Installment.client_id.in_(client_ids)))
            db.execute(delete(CaseFee).where(CaseFee.client_id.in_(client_ids)))
            db.execute(delete(Invoice).where(Invoice.client_id.in_(client_ids)))
            db.execute(delete(AuditLog).where(AuditLog.entity_type == "client", AuditLog.entity_id.in_(client_ids)))
        if matter_ids:
            db.execute(delete(ReceiptVoucher).where(ReceiptVoucher.matter_id.in_(matter_ids)))
            db.execute(delete(PaymentVoucher).where(PaymentVoucher.matter_id.in_(matter_ids)))
            db.execute(delete(Expense).where(Expense.matter_id.in_(matter_ids)))
            db.execute(delete(Document).where(Document.matter_id.in_(matter_ids)))
            db.execute(delete(CourtSession).where(CourtSession.matter_id.in_(matter_ids)))
            db.execute(delete(Task).where(Task.matter_id.in_(matter_ids)))
            db.execute(delete(WhatsAppLog).where(WhatsAppLog.matter_id.in_(matter_ids)))
            db.execute(delete(Installment).where(Installment.matter_id.in_(matter_ids)))
            db.execute(delete(CaseFee).where(CaseFee.matter_id.in_(matter_ids)))
            db.execute(delete(Invoice).where(Invoice.matter_id.in_(matter_ids)))
            db.execute(delete(AuditLog).where(AuditLog.entity_type == "matter", AuditLog.entity_id.in_(matter_ids)))

    db.execute(delete(Matter))
    db.execute(delete(Client))


def row_text_from_item(item: dict[str, Any]) -> str:
    if item.get("row_text"):
        return item["row_text"]
    parts = [
        f"رقم الدعوى: {item.get('case_number') or '-'}",
        f"تاريخ التسجيل: {item.get('registration_date') or '-'}",
        f"درجة التقاضي: {item.get('litigation_degree') or '-'}",
        f"الفئة: {item.get('case_category') or '-'}",
        f"المحكمة: {item.get('court_name') or '-'}",
        f"حالة الدعوى: {item.get('status_text') or '-'}",
        f"الطرف الأول: {item.get('party_one') or '-'}",
        f"الطرف الثاني: {item.get('party_two') or '-'}",
    ]
    return "\n".join(parts)


def ensure_session_for_matter(db: Session, *, matter: Matter, item: dict[str, Any], opened_at: date | None, status: str) -> None:
    if status not in {"court_session", "closed"} or not opened_at:
        return
    existing = db.scalar(select(CourtSession).where(CourtSession.matter_id == matter.id).limit(1))
    decision = None
    session_status = "scheduled"
    next_action = "متابعة موعد الجلسة من بوابة المجلس الأعلى للقضاء."
    notes = f"حالة الدعوى في ملف المجلس الأعلى للقضاء: {item.get('status_text') or '-'}."
    if status == "closed":
        session_status = "completed"
        decision = "محكوم حسب حالة الدعوى في ملف المجلس الأعلى للقضاء."
        next_action = "مراجعة منطوق الحكم وإدخال تفاصيله عند توفر نسخة الحكم."
    notes = (
        f"{notes}\n"
        "لم يظهر في جدول PDF تاريخ جلسة مستقل؛ تم استخدام تاريخ التسجيل كتاريخ متابعة مؤقت."
    )
    if existing:
        existing.session_date = opened_at
        existing.court_name = matter.court_name or item.get("court_name") or "المحكمة"
        existing.session_status = session_status
        existing.decision_summary = decision
        existing.next_action = next_action
        existing.notes = notes
        return
    db.add(
        CourtSession(
            matter_id=matter.id,
            session_date=opened_at,
            court_name=matter.court_name or item.get("court_name") or "المحكمة",
            session_status=session_status,
            decision_summary=decision,
            next_action=next_action,
            notes=notes,
        )
    )


def import_cases(db: Session, cases: list[dict[str, Any]], *, append: bool) -> tuple[int, int]:
    if not append:
        delete_existing_client_matter_data(db)

    clients_by_name = {client_name_key(client.full_name): client for client in db.scalars(select(Client)).all()}
    imported_matters = 0

    for index, item in enumerate(cases, start=1):
        real_case_number = normalize_space(item.get("case_number", ""))
        if not real_case_number:
            continue

        row_text = row_text_from_item(item)
        client_name = extract_client_name(item)
        client_key = client_name_key(client_name)
        client = clients_by_name.get(client_key)
        if not client:
            client = Client(
                full_name=client_name,
                client_type="company" if is_company(client_name) else "individual",
                company_name=client_name if is_company(client_name) else None,
                notes="مستورد من بيانات المجلس الأعلى للقضاء. اسم العميل مستخرج آلياً من نص PDF وقد يحتاج مراجعة.",
            )
            db.add(client)
            db.flush()
            clients_by_name[client_key] = client

        opened_at = registration_date(item)
        office_year = item.get("source_year") or (opened_at.year if opened_at else date.today().year)
        status = detect_status(item, row_text)
        case_type = case_type_from_item(item)
        matter = db.scalar(select(Matter).where(Matter.ministry_case_number == real_case_number))
        if not matter:
            matter = Matter(case_number=f"OFF-{office_year}-{index:04d}", ministry_case_number=real_case_number)
            db.add(matter)
        matter.title = f"{case_type} - {real_case_number}"
        matter.client_id = client.id
        matter.assigned_lawyer_id = preferred_lawyer_id(db, item)
        matter.case_type = case_type
        matter.court_name = court_name_from_item(item)
        matter.court_level = court_level_from_item(item)
        matter.opponent_name = extract_opponent_name(item, client_name)
        matter.status = status
        matter.priority = "medium"
        matter.description = row_text
        matter.opened_at = opened_at
        matter.closed_at = opened_at if status == "closed" else None
        db.flush()
        ensure_session_for_matter(db, matter=matter, item=item, opened_at=opened_at, status=status)
        imported_matters += 1

    db.flush()
    return len(clients_by_name), imported_matters


def main() -> None:
    args = parse_args()

    backup_path = None
    if not args.append and not args.no_backup:
        backup_path = backup_database()

    cases = load_input_cases(args.input_files)
    with SessionLocal() as db:
        client_count, matter_count = import_cases(db, cases, append=args.append)
        db.commit()

    if backup_path:
        print(f"Backup: {backup_path}")
    print(f"Imported clients: {client_count}")
    print(f"Imported matters: {matter_count}")
    print(f"Database: {database_file() or PROJECT_ROOT}")


if __name__ == "__main__":
    main()

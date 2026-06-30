from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
import re
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Client, Document, Invoice, Matter, OfficeSetting, User

DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0640]")
CLIENT_NAME_STOP_WORDS = {"بن", "بنت", "ابن", "إبن", "ابنة"}

MATTER_CASE_TYPES = [
    "مدني",
    "تجاري",
    "جزائي",
    "أحوال شخصية",
    "عمالي",
    "عقاري",
    "إداري",
    "تنفيذ",
    "استثمار وتجارة",
    "إيجارات",
    "تركات",
    "تحكيم",
    "استشارة قانونية",
    "أخرى",
]

COURT_NAMES = [
    "المحكمة العليا",
    "محكمة الاستئناف بمسقط",
    "محكمة الاستئناف بالسيب",
    "محكمة الاستئناف بنزوى",
    "محكمة الاستئناف بالرستاق",
    "محكمة الاستئناف بصحار",
    "محكمة الاستئناف بإبراء",
    "محكمة الاستئناف بالبريمي",
    "محكمة الاستئناف بصلالة",
    "محكمة الاستئناف بالدقم",
    "محكمة الاستئناف بمسندم",
    "المحكمة الابتدائية بمسقط",
    "المحكمة الابتدائية بالسيب",
    "المحكمة الابتدائية بقريات",
    "المحكمة الابتدائية ببوشر",
    "المحكمة الابتدائية بنزوى",
    "المحكمة الابتدائية ببهلا",
    "المحكمة الابتدائية بسمائل",
    "المحكمة الابتدائية ببركاء",
    "المحكمة الابتدائية بالرستاق",
    "المحكمة الابتدائية بالمصنعة",
    "المحكمة الابتدائية بصحار",
    "المحكمة الابتدائية بصحم",
    "المحكمة الابتدائية بالسويق",
    "المحكمة الابتدائية بإبراء",
    "المحكمة الابتدائية بالمضيبي",
    "المحكمة الابتدائية بالبريمي",
    "المحكمة الابتدائية بعبري",
    "المحكمة الابتدائية بخصب",
    "المحكمة الابتدائية بصلالة",
    "المحكمة الابتدائية بالدقم",
    "محكمة الاستثمار والتجارة",
    "دائرة التنفيذ",
]

COURT_LEVELS = [
    "ابتدائي",
    "استئناف",
    "عليا",
    "طعن أمام المحكمة العليا",
    "تنفيذ",
    "دائرة إدارية",
    "دائرة جزائية",
    "دائرة تجارية",
    "دائرة عمالية",
    "دائرة أحوال شخصية",
    "لجنة تسوية ومصالحة",
    "تحكيم",
]

MATTER_TITLE_SUGGESTIONS = [
    "مطالبة مالية",
    "نزاع تجاري",
    "دعوى عمالية",
    "نزاع عقاري",
    "أحوال شخصية",
    "تنفيذ حكم",
    "استئناف حكم",
    "استشارة ومراجعة عقد",
]


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_time(value: str | None) -> time | None:
    if not value:
        return None
    return datetime.strptime(value, "%H:%M").time()


def parse_decimal(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    return Decimal(value)


def none_if_empty(value: str | None) -> str | None:
    value = value.strip() if value else ""
    return value or None


def normalize_arabic_name(value: str | None) -> str:
    value = DIACRITICS_RE.sub("", value or "")
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    value = re.sub(r"[^\w\s\u0600-\u06ff]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def client_name_key(value: str | None) -> str:
    words = [
        word
        for word in normalize_arabic_name(value).split()
        if word not in CLIENT_NAME_STOP_WORDS
    ]
    return " ".join(words)


def _is_subsequence(shorter: list[str], longer: list[str]) -> bool:
    position = 0
    for word in longer:
        if position < len(shorter) and shorter[position] == word:
            position += 1
    return position == len(shorter)


def client_names_match(left: str | None, right: str | None) -> bool:
    left_key = client_name_key(left)
    right_key = client_name_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_words = left_key.split()
    right_words = right_key.split()
    if len(left_words) < 3 or len(right_words) < 3:
        return False
    shorter, longer = (left_words, right_words) if len(left_words) <= len(right_words) else (right_words, left_words)
    return _is_subsequence(shorter, longer)


def _same_or_empty(left: str | None, right: str | None) -> bool:
    left_value = (left or "").strip()
    right_value = (right or "").strip()
    return not left_value or not right_value or left_value == right_value


def find_similar_client(
    db: Session,
    full_name: str,
    *,
    exclude_client_id: int | None = None,
    phone: str | None = None,
    civil_id: str | None = None,
    commercial_registration: str | None = None,
) -> Client | None:
    for client in db.scalars(select(Client).order_by(Client.id)).all():
        if exclude_client_id and client.id == exclude_client_id:
            continue
        if not client_names_match(full_name, client.full_name):
            continue
        if not _same_or_empty(phone, client.phone):
            continue
        if not _same_or_empty(civil_id, client.civil_id):
            continue
        if not _same_or_empty(commercial_registration, client.commercial_registration):
            continue
        return client
    return None


def int_or_none(value: str | int | None) -> int | None:
    if value in (None, "", "0"):
        return None
    return int(value)


def search_clients(stmt: Select, q: str | None) -> Select:
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Client.full_name.ilike(like), Client.phone.ilike(like), Client.civil_id.ilike(like)))
    return stmt


def get_form_context(db: Session) -> dict:
    return {
        "clients": db.query(Client).order_by(Client.full_name).all(),
        "lawyers": db.query(User).filter(User.role.in_(["lawyer", "admin"]), User.is_active.is_(True)).order_by(User.full_name).all(),
        "users": db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all(),
        "matters": db.query(Matter).filter(Matter.status != "archived").order_by(Matter.case_number.desc()).all(),
        "invoices": db.query(Invoice).order_by(Invoice.issue_date.desc(), Invoice.id.desc()).all(),
        "matter_case_types": MATTER_CASE_TYPES,
        "court_names": COURT_NAMES,
        "court_levels": COURT_LEVELS,
        "matter_title_suggestions": MATTER_TITLE_SUGGESTIONS,
    }


def setting_value(db: Session, key: str, default: str = "") -> str:
    setting = db.query(OfficeSetting).filter(OfficeSetting.key == key).first()
    return setting.value if setting and setting.value else default


async def save_upload(file: UploadFile) -> tuple[str, str, int, str | None]:
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    original = Path(file.filename or "document").name
    suffix = Path(original).suffix
    stored_name = f"{uuid4().hex}{suffix}"
    path = upload_dir / stored_name
    content = await file.read()
    path.write_bytes(content)
    return f"/static/uploads/{stored_name}", original, len(content), file.content_type


def can_see_document(user: User, document: Document) -> bool:
    return not document.is_confidential or user.role in {"admin", "lawyer"}

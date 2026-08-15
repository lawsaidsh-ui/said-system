import html
import json
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Client, CourtDocumentTemplate, GeneratedCourtDocument, Matter, OfficeSetting, User
from app.routes.helpers import setting_value


COURT_TEMPLATE_CATEGORIES = [
    "خطابات المحكمة الابتدائية",
    "خطابات محكمة الاستئناف",
    "خطابات المحكمة العليا",
    "خطابات دوائر التنفيذ",
    "خطابات الادعاء العام",
    "خطابات الجهات الحكومية",
    "خطابات الخبراء",
    "خطابات عامة",
]

LETTER_VARIABLES = [
    ("client_name", "اسم العميل"),
    ("client_civil_id", "الرقم المدني للعميل"),
    ("client_phone", "هاتف العميل"),
    ("matter_number", "رقم القضية"),
    ("matter_title", "عنوان القضية"),
    ("matter_type", "نوع القضية"),
    ("court_name", "المحكمة أو الجهة"),
    ("court_department", "الدائرة أو القسم"),
    ("opponent_name", "اسم الخصم"),
    ("session_date", "تاريخ الجلسة"),
    ("letter_subject", "موضوع الخطاب"),
    ("letter_date", "تاريخ الخطاب"),
    ("letter_content", "محتوى إضافي"),
    ("reference_number", "الرقم المرجعي"),
    ("user_name", "اسم المستخدم"),
    ("user_job_title", "المسمى الوظيفي"),
    ("office_name", "اسم المكتب"),
]

VARIABLE_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
SAFE_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}
MAX_IMAGE_SIZE = 2 * 1024 * 1024


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads_map(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def extract_variables(*parts: str | None) -> list[str]:
    names: set[str] = set()
    for part in parts:
        names.update(VARIABLE_RE.findall(part or ""))
    return sorted(names)


def sanitize_template_html(value: str) -> str:
    try:
        import bleach
    except ImportError:
        value = re.sub(r"<\s*(script|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", "", value, flags=re.I | re.S)
        value = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", value, flags=re.I | re.S)
        return value
    return bleach.clean(
        value,
        tags=[
            "p",
            "br",
            "strong",
            "b",
            "em",
            "u",
            "h1",
            "h2",
            "h3",
            "ul",
            "ol",
            "li",
            "table",
            "thead",
            "tbody",
            "tr",
            "td",
            "th",
            "div",
            "span",
        ],
        attributes={"*": ["style", "dir", "class"], "td": ["colspan", "rowspan"], "th": ["colspan", "rowspan"]},
        protocols=[],
        strip=True,
    )


def replace_variables(text: str, values: dict[str, object]) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        value = values.get(key)
        return html.escape(str(value)) if value not in (None, "") else match.group(0)

    return VARIABLE_RE.sub(repl, text or "")


def collect_auto_values(
    db: Session,
    *,
    client: Client | None,
    matter: Matter | None,
    user: User,
    court_name: str | None,
    department_name: str | None,
    subject: str | None,
    reference_number: str | None = None,
) -> dict[str, str]:
    latest_session = None
    if matter:
        latest_session = sorted(matter.sessions, key=lambda item: item.session_date or date.min, reverse=True)[0] if matter.sessions else None
    return {
        "client_name": client.full_name if client else "",
        "client_civil_id": client.civil_id if client else "",
        "client_phone": client.phone if client else "",
        "matter_number": matter.case_number if matter else "",
        "matter_title": matter.title if matter else "",
        "matter_type": matter.case_type if matter else "",
        "court_name": court_name or (matter.court_name if matter else ""),
        "court_department": department_name or "",
        "opponent_name": matter.opponent_name if matter else "",
        "session_date": latest_session.session_date.isoformat() if latest_session and latest_session.session_date else "",
        "letter_subject": subject or "",
        "letter_date": date.today().isoformat(),
        "letter_content": "",
        "reference_number": reference_number or "",
        "user_name": user.full_name,
        "user_job_title": user.job_title or "",
        "office_name": setting_value(db, "office_name", "مكتب سعيد الشبيبي للمحاماة"),
    }


def missing_variables(template: CourtDocumentTemplate, values: dict[str, object]) -> list[str]:
    required = set(loads_map(template.variables_schema).get("variables", []))
    if not required:
        required = set(extract_variables(template.subject_template, template.body_html))
    return sorted(name for name in required if not values.get(name))


def build_document_html(
    db: Session,
    *,
    template: CourtDocumentTemplate | None,
    subject: str,
    body_html: str,
    values: dict[str, object],
    user: User,
    reference_number: str | None,
    include_letterhead: bool,
    include_signature: bool,
    include_stamp: bool,
) -> str:
    letterhead = setting_value(db, "court_letterhead_path")
    stamp = setting_value(db, "court_stamp_path")
    footer = setting_value(db, "court_letter_footer", setting_value(db, "invoice_footer", ""))
    contact = setting_value(db, "court_contact_details", "")
    rendered_subject = replace_variables(subject, values)
    rendered_body = replace_variables(body_html, values)
    signature_html = ""
    if include_signature:
        signature_img = f'<img src="{user.signature_path}" alt="التوقيع">' if user.signature_path else ""
        signature_html = f"""
        <div class="signature-block">
          {signature_img}
          <strong>{html.escape(user.full_name)}</strong>
          <span>{html.escape(user.job_title or "")}</span>
        </div>
        """
    stamp_html = f'<img class="stamp-img" src="{stamp}" alt="ختم المكتب">' if include_stamp and stamp else ""
    letterhead_html = f'<img class="letterhead-img" src="{letterhead}" alt="اللتر هيد">' if include_letterhead and letterhead else f"<h1>{html.escape(values.get('office_name', 'مكتب سعيد الشبيبي للمحاماة'))}</h1>"
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4; margin: 18mm 16mm 18mm 16mm; }}
    body {{ direction: rtl; font-family: 'Noto Naskh Arabic', 'Noto Sans Arabic', 'Tajawal', Arial, sans-serif; color: #162033; line-height: 1.9; }}
    .letterhead {{ text-align: center; border-bottom: 1px solid #d9dee8; padding-bottom: 12px; margin-bottom: 18px; }}
    .letterhead h1 {{ margin: 0; font-size: 24px; color: #0f2742; }}
    .letterhead-img {{ width: 100%; max-height: 130px; object-fit: contain; }}
    .meta {{ display: grid; gap: 4px; margin-bottom: 18px; font-size: 13px; color: #334155; }}
    .subject {{ font-size: 18px; font-weight: 700; color: #0f2742; margin: 16px 0; }}
    .body table {{ width: 100%; border-collapse: collapse; }}
    .body td, .body th {{ border: 1px solid #d9dee8; padding: 6px 8px; }}
    .sign-area {{ break-inside: avoid; display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-top: 34px; }}
    .signature-block {{ min-width: 220px; display: grid; gap: 4px; }}
    .signature-block img {{ max-width: 220px; max-height: 90px; object-fit: contain; }}
    .stamp-img {{ width: 130px; max-height: 130px; object-fit: contain; }}
    .footer {{ border-top: 1px solid #d9dee8; margin-top: 24px; padding-top: 10px; font-size: 12px; color: #64748b; text-align: center; }}
  </style>
</head>
<body>
  <header class="letterhead">{letterhead_html}</header>
  <section class="meta">
    <div>الرقم المرجعي: {html.escape(reference_number or "يحدد عند الإصدار")}</div>
    <div>التاريخ: {html.escape(str(values.get("letter_date") or date.today().isoformat()))}</div>
    <div>إلى: {html.escape(str(values.get("court_name") or ""))}</div>
    <div>الدائرة/القسم: {html.escape(str(values.get("court_department") or ""))}</div>
  </section>
  <h2 class="subject">{rendered_subject}</h2>
  <main class="body">{rendered_body}</main>
  <section class="sign-area">{signature_html}{stamp_html}</section>
  <footer class="footer">{html.escape(footer)}<br>{html.escape(contact)}</footer>
</body>
</html>"""


def next_reference_number(db: Session) -> str:
    pattern = setting_value(db, "court_reference_format", "SSL/COURT/{year}/{seq:04d}")
    year = date.today().year
    count = db.scalar(
        select(func.count(GeneratedCourtDocument.id)).where(
            GeneratedCourtDocument.reference_number.is_not(None),
            GeneratedCourtDocument.issued_at >= datetime(year, 1, 1),
        )
    ) or 0
    return pattern.replace("{year}", str(year)).replace("{seq:04d}", f"{count + 1:04d}").replace("{seq}", str(count + 1))


def generate_pdf(html_content: str, reference_number: str) -> tuple[str, str, int]:
    settings = get_settings()
    output_dir = Path(settings.upload_dir) / "court-documents"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_ref = re.sub(r"[^A-Za-z0-9_-]+", "-", reference_number).strip("-")
    stored_name = f"{safe_ref}-{uuid4().hex[:8]}.pdf"
    path = output_dir / stored_name
    try:
        from weasyprint import HTML
        HTML(string=html_content, base_url=str(Path.cwd())).write_pdf(str(path))
    except (ImportError, OSError):
        _generate_pdf_reportlab(html_content, path)
    return f"/static/uploads/court-documents/{stored_name}", stored_name, path.stat().st_size


def _html_to_text(html_content: str) -> str:
    text = re.sub(r"</(p|div|h1|h2|h3|li|tr)>", "\n", html_content, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _font_path() -> str | None:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _rtl_text(value: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return value
    return get_display(arabic_reshaper.reshape(value))


def _generate_pdf_reportlab(html_content: str, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    width, height = A4
    font_name = "Helvetica"
    font_path = _font_path()
    if font_path:
        font_name = "ArabicFallback"
        pdfmetrics.registerFont(TTFont(font_name, font_path))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle("Court Document")
    margin_x = 48
    y = height - 54
    line_height = 19
    pdf.setFont(font_name, 12)
    for paragraph in _html_to_text(html_content).splitlines():
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if pdf.stringWidth(_rtl_text(candidate), font_name, 12) > width - (margin_x * 2):
                pdf.drawRightString(width - margin_x, y, _rtl_text(current))
                y -= line_height
                current = word
            else:
                current = candidate
            if y < 54:
                pdf.showPage()
                pdf.setFont(font_name, 12)
                y = height - 54
        if current:
            pdf.drawRightString(width - margin_x, y, _rtl_text(current))
            y -= line_height
        y -= 5
        if y < 54:
            pdf.showPage()
            pdf.setFont(font_name, 12)
            y = height - 54
    pdf.save()


async def save_secure_image(file: UploadFile, folder: str) -> str:
    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="حجم الصورة أكبر من الحد المسموح.")
    suffix = SAFE_IMAGE_TYPES.get(file.content_type or "")
    if not suffix:
        raise HTTPException(status_code=400, detail="نوع الصورة غير مدعوم.")
    upload_dir = Path(get_settings().upload_dir) / folder
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{suffix}"
    path = upload_dir / stored_name
    path.write_bytes(content)
    return f"/static/uploads/{folder}/{stored_name}"


def snapshot_asset(path_value: str | None, folder: str) -> str | None:
    if not path_value or not path_value.startswith("/static/uploads/"):
        return path_value
    source = Path("app/static") / path_value.removeprefix("/static/").lstrip("/")
    if not source.exists():
        return path_value
    target_dir = Path(get_settings().upload_dir) / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid4().hex}{source.suffix}"
    shutil.copy2(source, target)
    return f"/static/uploads/{folder}/{target.name}"

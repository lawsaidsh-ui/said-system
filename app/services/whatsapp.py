import re
from datetime import date
from decimal import Decimal
from string import Formatter
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Appointment, Client, CourtSession, Installment, Invoice, Matter, OfficeSetting, Payment, User, WhatsAppTemplate


WHATSAPP_TEMPLATE_TYPES = {
    "appointment_confirmation": "تأكيد موعد",
    "payment_reminder": "تذكير بالسداد",
    "hearing_reminder": "تذكير بموعد جلسة",
    "installment_reminder": "تذكير بموعد قسط",
    "documents_request": "طلب استكمال مستندات",
    "case_status_update": "تحديث حالة القضية",
    "general": "رسالة عامة مخصصة",
}

WHATSAPP_VARIABLES = [
    "client_name",
    "case_number",
    "case_type",
    "hearing_date",
    "hearing_time",
    "due_amount",
    "due_date",
    "appointment_date",
    "appointment_time",
    "office_name",
    "office_address",
]

UNKNOWN_VALUE = "غير محدد"
APPOINTMENT_LOCATION_URL = "https://share.google/7J0oN8LceXgWsde3U"

DEFAULT_TEMPLATES = [
    (
        "appointment_confirmation",
        "تأكيد موعد العميل",
        "الأستاذ/ة {client_name}\nتم تأكيد موعدكم لدى {office_name} بتاريخ {appointment_date} الساعة {appointment_time}.\nعنوان المكتب: {office_address}\nيرجى الحضور قبل الموعد بوقت كافٍ، وننبهكم أن التأخر عن الموعد قد يؤدي إلى إلغائه أو إعادة جدولته حسب توفر المواعيد.\nمع التحية، {office_name}",
    ),
    (
        "payment_reminder",
        "تذكير بالسداد",
        "الأستاذ/ة {client_name}\nنذكركم بسداد المبلغ المستحق {due_amount} بتاريخ استحقاق {due_date} بخصوص القضية رقم {case_number}.\nمع التحية، {office_name}",
    ),
    (
        "hearing_reminder",
        "تذكير بموعد جلسة",
        "الأستاذ/ة {client_name}\nنذكركم بموعد الجلسة في القضية رقم {case_number} بتاريخ {hearing_date} الساعة {hearing_time}.\nمع التحية، {office_name}",
    ),
    (
        "installment_reminder",
        "تذكير بموعد قسط",
        "الأستاذ/ة {client_name}\nنذكركم بموعد القسط المستحق بمبلغ {due_amount} بتاريخ {due_date} بخصوص القضية رقم {case_number}.\nمع التحية، {office_name}",
    ),
    (
        "documents_request",
        "طلب استكمال مستندات",
        "الأستاذ/ة {client_name}\nنرجو استكمال المستندات المطلوبة بخصوص القضية رقم {case_number} حتى نتمكن من متابعة الإجراءات.\nمع التحية، {office_name}",
    ),
    (
        "case_status_update",
        "تحديث حالة القضية",
        "الأستاذ/ة {client_name}\nنود إفادتكم بوجود تحديث على القضية رقم {case_number}، نوع القضية: {case_type}.\nمع التحية، {office_name}",
    ),
    (
        "general",
        "رسالة عامة مخصصة",
        "الأستاذ/ة {client_name}\n\nمع التحية، {office_name}",
    ),
]


def ensure_default_templates(db: Session) -> None:
    templates = db.scalars(select(WhatsAppTemplate)).all()
    existing = {item.template_type for item in templates}
    changed = False
    for item in templates:
        if item.template_type == "appointment_confirmation" and APPOINTMENT_LOCATION_URL not in item.body:
            item.body = f"{item.body.rstrip()}\n{APPOINTMENT_LOCATION_URL}"
            changed = True
    for template_type, name, body in DEFAULT_TEMPLATES:
        if template_type not in existing:
            if template_type == "appointment_confirmation" and APPOINTMENT_LOCATION_URL not in body:
                body = f"{body.rstrip()}\n{APPOINTMENT_LOCATION_URL}"
            db.add(WhatsAppTemplate(template_type=template_type, name=name, body=body, is_active=True))
            changed = True
    if changed:
        db.commit()


def normalize_phone(phone: str | None) -> tuple[str | None, str | None]:
    raw = (phone or "").strip()
    if not raw:
        return None, "رقم الهاتف غير موجود."
    if raw.startswith("+"):
        raw = raw[1:]
    cleaned = re.sub(r"\D+", "", raw)
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    if len(cleaned) == 8 and cleaned[0] in {"9", "7"}:
        cleaned = f"968{cleaned}"
    if cleaned.startswith("0"):
        return None, "رقم الهاتف يجب أن يحتوي على رمز الدولة، أو رقم عماني يبدأ بـ 9 أو 7."
    if not cleaned.isdigit() or len(cleaned) < 8 or len(cleaned) > 15:
        return None, "رقم الهاتف غير صالح."
    return cleaned, None


def whatsapp_url(phone: str, message: str) -> str:
    return f"https://wa.me/{phone}?text={quote(message)}"


def format_decimal(value: Decimal | int | float | None) -> str:
    if value is None:
        return "-"
    return f"{Decimal(value):.2f}"


def merge_variables(base: dict[str, str], extra: dict[str, str] | None) -> dict[str, str]:
    merged = dict(base)
    if extra:
        for key, value in extra.items():
            if value not in (None, "", "-", UNKNOWN_VALUE):
                merged[key] = str(value)
    return merged


def office_name(db: Session) -> str:
    setting = db.scalar(select(OfficeSetting).where(OfficeSetting.key == "office_name"))
    return setting.value if setting and setting.value else "مكتب سعيد الشبيبي للمحاماة"


def office_address(db: Session) -> str:
    setting = db.scalar(select(OfficeSetting).where(OfficeSetting.key == "address"))
    return setting.value if setting and setting.value else "مسقط، سلطنة عمان"


def format_time12(value) -> str:
    if not value:
        return UNKNOWN_VALUE
    hour = value.hour % 12 or 12
    minute = value.strftime("%M")
    period = "م" if value.hour >= 12 else "ص"
    return f"{hour}:{minute} {period}"


def render_template(body: str, variables: dict[str, str]) -> str:
    allowed = set(WHATSAPP_VARIABLES)
    values = {key: variables.get(key) or "-" for key in allowed}
    parts: list[str] = []
    for literal, field_name, format_spec, conversion in Formatter().parse(body):
        parts.append(literal)
        if field_name is None:
            continue
        if field_name in allowed:
            parts.append(format(values[field_name], format_spec) if format_spec else values[field_name])
        else:
            parts.append("{" + field_name + "}")
    return "".join(parts)


def invoice_variables(invoice: Invoice | None) -> dict[str, str]:
    if not invoice:
        return {}
    remaining = (invoice.total_amount or Decimal("0")) - (invoice.paid_amount or Decimal("0"))
    matter = invoice.matter
    return {
        "due_amount": format_decimal(remaining if remaining > 0 else invoice.total_amount),
        "due_date": str(invoice.due_date or invoice.issue_date or UNKNOWN_VALUE),
        "case_number": matter.case_number if matter else "-",
        "case_type": matter.case_type or matter.title if matter else "-",
    }


def installment_variables(installment: Installment | None) -> dict[str, str]:
    if not installment:
        return {}
    remaining = (installment.amount or Decimal("0")) - (installment.paid_amount or Decimal("0"))
    matter = installment.matter
    return {
        "due_amount": format_decimal(remaining if remaining > 0 else installment.amount),
        "due_date": str(installment.due_date or UNKNOWN_VALUE),
        "case_number": matter.case_number if matter else "-",
        "case_type": matter.case_type or matter.title if matter else "-",
    }


def session_variables(session: CourtSession | None) -> dict[str, str]:
    if not session:
        return {}
    matter = session.matter
    return {
        "hearing_date": str(session.session_date or UNKNOWN_VALUE),
        "hearing_time": session.session_time.strftime("%H:%M") if session.session_time else UNKNOWN_VALUE,
        "case_number": matter.case_number if matter else "-",
        "case_type": matter.case_type or matter.title if matter else "-",
    }


def next_due_invoice(db: Session, *, client_id: int | None = None, matter_id: int | None = None) -> Invoice | None:
    stmt = (
        select(Invoice)
        .options(selectinload(Invoice.matter))
        .where(Invoice.status.in_(["unpaid", "partially_paid", "overdue", "sent"]))
        .order_by(Invoice.due_date.is_(None), Invoice.due_date.asc(), Invoice.issue_date.asc())
    )
    if matter_id:
        stmt = stmt.where(Invoice.matter_id == matter_id)
    elif client_id:
        stmt = stmt.where(Invoice.client_id == client_id)
    else:
        return None
    return db.scalar(stmt)


def next_due_installment(db: Session, *, client_id: int | None = None, matter_id: int | None = None) -> Installment | None:
    stmt = (
        select(Installment)
        .options(selectinload(Installment.matter))
        .where(Installment.status.in_(["pending", "overdue", "partial"]))
        .order_by(Installment.due_date.asc())
    )
    if matter_id:
        stmt = stmt.where(Installment.matter_id == matter_id)
    elif client_id:
        stmt = stmt.where(Installment.client_id == client_id)
    else:
        return None
    return db.scalar(stmt)


def next_hearing(db: Session, *, client_id: int | None = None, matter_id: int | None = None) -> CourtSession | None:
    stmt = (
        select(CourtSession)
        .join(Matter)
        .options(selectinload(CourtSession.matter))
        .where(CourtSession.session_date >= date.today())
        .order_by(CourtSession.session_date.asc(), CourtSession.session_time.asc())
    )
    if matter_id:
        stmt = stmt.where(CourtSession.matter_id == matter_id)
    elif client_id:
        stmt = stmt.where(Matter.client_id == client_id)
    else:
        return None
    return db.scalar(stmt)


def enrich_context_from_related_records(db: Session, context: dict) -> None:
    client = context["client"]
    matter = context["matter"]
    client_id = client.id if client else None
    matter_id = matter.id if matter else None
    invoice_vars = invoice_variables(next_due_invoice(db, client_id=client_id, matter_id=matter_id))
    installment_vars = installment_variables(next_due_installment(db, client_id=client_id, matter_id=matter_id))
    hearing_vars = session_variables(next_hearing(db, client_id=client_id, matter_id=matter_id))

    template_variables = dict(context.get("template_variables") or {})
    template_variables.setdefault("payment_reminder", merge_variables(context["variables"], invoice_vars or installment_vars))
    template_variables.setdefault("installment_reminder", merge_variables(context["variables"], installment_vars or invoice_vars))
    template_variables.setdefault("hearing_reminder", merge_variables(context["variables"], hearing_vars))
    context["template_variables"] = template_variables
    for extra in (invoice_vars, installment_vars, hearing_vars):
        for key, value in extra.items():
            if context["variables"].get(key) in (None, "-", UNKNOWN_VALUE) and value not in (None, "", "-", UNKNOWN_VALUE):
                context["variables"][key] = str(value)


def source_context(db: Session, source_type: str, source_id: int) -> dict:
    context = {
        "client": None,
        "matter": None,
        "phone_raw": "",
        "variables": {
            "client_name": UNKNOWN_VALUE,
            "case_number": UNKNOWN_VALUE,
            "case_type": UNKNOWN_VALUE,
            "hearing_date": UNKNOWN_VALUE,
            "hearing_time": UNKNOWN_VALUE,
            "due_amount": UNKNOWN_VALUE,
            "due_date": UNKNOWN_VALUE,
            "appointment_date": UNKNOWN_VALUE,
            "appointment_time": UNKNOWN_VALUE,
            "office_name": office_name(db),
            "office_address": office_address(db),
        },
        "template_variables": {},
    }

    if source_type == "appointment":
        appointment = db.get(Appointment, source_id)
        if not appointment:
            raise ValueError("appointment")
        context["phone_raw"] = appointment.phone or ""
        context["variables"]["client_name"] = appointment.client_name or UNKNOWN_VALUE
        context["variables"]["case_type"] = appointment.case_type or appointment.topic or "-"
        context["variables"]["appointment_date"] = str(appointment.appointment_date or UNKNOWN_VALUE)
        context["variables"]["appointment_time"] = format_time12(appointment.appointment_time)
        context["template_variables"]["appointment_confirmation"] = dict(context["variables"])
    elif source_type == "client":
        client = db.get(Client, source_id)
        if not client:
            raise ValueError("client")
        context["client"] = client
    elif source_type == "matter":
        matter = db.scalar(select(Matter).where(Matter.id == source_id).options(selectinload(Matter.client)))
        if not matter:
            raise ValueError("matter")
        context["matter"] = matter
        context["client"] = matter.client
        context["variables"]["case_number"] = matter.case_number
        context["variables"]["case_type"] = matter.case_type or matter.title or "-"
    elif source_type == "payment":
        payment = db.scalar(
            select(Payment)
            .where(Payment.id == source_id)
            .options(selectinload(Payment.invoice).selectinload(Invoice.client), selectinload(Payment.invoice).selectinload(Invoice.matter))
        )
        if not payment or not payment.invoice:
            raise ValueError("payment")
        invoice = payment.invoice
        context["client"] = invoice.client
        context["matter"] = invoice.matter
        payment_vars = invoice_variables(invoice)
        if not payment_vars.get("due_amount") or payment_vars.get("due_amount") == "-":
            payment_vars["due_amount"] = format_decimal(payment.amount)
        payment_vars["due_date"] = str(invoice.due_date or payment.payment_date or "-")
        context["variables"].update(payment_vars)
        context["template_variables"]["payment_reminder"] = merge_variables(context["variables"], payment_vars)
        if invoice.matter:
            context["variables"]["case_number"] = invoice.matter.case_number
            context["variables"]["case_type"] = invoice.matter.case_type or invoice.matter.title or "-"
    elif source_type == "installment":
        installment = db.scalar(
            select(Installment)
            .where(Installment.id == source_id)
            .options(selectinload(Installment.client), selectinload(Installment.matter))
        )
        if not installment:
            raise ValueError("installment")
        context["client"] = installment.client
        context["matter"] = installment.matter
        vars_for_installment = installment_variables(installment)
        context["variables"].update(vars_for_installment)
        context["template_variables"]["installment_reminder"] = merge_variables(context["variables"], vars_for_installment)
    elif source_type == "session":
        session = db.scalar(
            select(CourtSession)
            .where(CourtSession.id == source_id)
            .options(selectinload(CourtSession.matter).selectinload(Matter.client))
        )
        if not session:
            raise ValueError("session")
        matter = session.matter
        context["matter"] = matter
        context["client"] = matter.client if matter else None
        hearing_vars = session_variables(session)
        context["variables"].update(hearing_vars)
        context["template_variables"]["hearing_reminder"] = merge_variables(context["variables"], hearing_vars)
        if matter:
            context["variables"]["case_number"] = matter.case_number
            context["variables"]["case_type"] = matter.case_type or matter.title or "-"
    else:
        raise ValueError("source_type")

    client = context["client"]
    matter = context["matter"]
    if client:
        context["phone_raw"] = client.phone or ""
        context["variables"]["client_name"] = client.full_name
    if matter:
        context["variables"]["case_number"] = matter.case_number
        context["variables"]["case_type"] = matter.case_type or matter.title or "-"
    context["template_variables"] = {
        key: merge_variables(context["variables"], values)
        for key, values in (context.get("template_variables") or {}).items()
    }
    enrich_context_from_related_records(db, context)
    return context


def template_options(db: Session, variables: dict[str, str], template_variables: dict[str, dict[str, str]] | None = None) -> list[dict]:
    ensure_default_templates(db)
    preferred_template_type = None
    if variables.get("appointment_date") not in (None, "", "-", UNKNOWN_VALUE):
        preferred_template_type = "appointment_confirmation"
    templates = db.scalars(select(WhatsAppTemplate).where(WhatsAppTemplate.is_active.is_(True)).order_by(WhatsAppTemplate.id)).all()
    if preferred_template_type:
        templates = sorted(templates, key=lambda item: (item.template_type != preferred_template_type, item.id))
    return [
        {
            "id": template.id,
            "name": template.name,
            "template_type": template.template_type,
            "label": WHATSAPP_TEMPLATE_TYPES.get(template.template_type, template.name),
            "body": template.body,
            "rendered": render_template(template.body, (template_variables or {}).get(template.template_type, variables)),
        }
        for template in templates
    ]


def employee_name(user: User | None) -> str:
    return user.full_name if user else "-"

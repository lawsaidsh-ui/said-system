import json
from typing import Any

from fastapi import Request
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.models import AuditLog, User


ACTION_LABELS = {
    "create_client": "إضافة عميل",
    "update_client": "تعديل بيانات عميل",
    "create_matter": "إضافة قضية",
    "update_matter": "تعديل قضية",
    "close_matter": "إغلاق قضية",
    "upload_document": "رفع مستند",
    "create_session": "إضافة جلسة",
    "update_session": "تعديل جلسة",
    "create_invoice": "إضافة فاتورة",
    "create_payment": "تسجيل دفعة",
    "open_overdue_whatsapp_reminder": "فتح تذكير واتساب للمتعثرات المالية",
    "create_fixed_monthly_expense": "إضافة مصروف شهري ثابت",
    "update_fixed_monthly_expense": "تعديل مصروف شهري ثابت",
    "toggle_fixed_monthly_expense": "إيقاف/تفعيل مصروف شهري ثابت",
    "delete_fixed_monthly_expense": "حذف مصروف شهري ثابت",
    "delete_expense": "حذف مصروف",
    "create_user": "إضافة مستخدم",
    "change_user_role": "تعديل صلاحيات مستخدم",
    "reset_user_password": "إعادة تعيين كلمة مرور مستخدم",
}

ENTITY_LABELS = {
    "client": "عميل",
    "matter": "قضية",
    "document": "مستند",
    "court_session": "جلسة",
    "invoice": "فاتورة",
    "payment": "دفعة",
    "user": "مستخدم",
    "system": "النظام",
    "case_fee": "أتعاب قضية",
    "receipt_voucher": "سند قبض",
    "payment_voucher": "سند صرف",
    "expense": "مصروف",
    "fixed_monthly_expense": "مصروف شهري ثابت",
    "salary_record": "راتب",
    "installment": "قسط",
    "journal_entry": "قيد محاسبي",
}


def log_action(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    ip_address = request.client.host if request and request.client else None
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value_json=json.dumps(old_value, ensure_ascii=False, default=str) if old_value else None,
            new_value_json=json.dumps(new_value, ensure_ascii=False, default=str) if new_value else None,
            ip_address=ip_address,
        )
    )


def audit_action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def audit_entity_label(entity_type: str) -> str:
    return ENTITY_LABELS.get(entity_type, entity_type)


def recent_audit_logs(db: Session, *, limit: int = 50) -> list[AuditLog]:
    return db.scalars(
        select(AuditLog)
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()


def audit_logs_for_targets(
    db: Session,
    targets: list[tuple[str, int | None]],
    *,
    limit: int = 12,
) -> list[AuditLog]:
    clauses = [
        and_(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        for entity_type, entity_id in targets
        if entity_id is not None
    ]
    if not clauses:
        return []
    return db.scalars(
        select(AuditLog)
        .where(or_(*clauses))
        .options(selectinload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    ).all()

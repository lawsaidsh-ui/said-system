ROLE_LABELS = {
    "admin": "مدير النظام",
    "lawyer": "محام",
    "secretary": "سكرتير",
    "accountant": "محاسب",
    "data_entry": "مدخل بيانات",
    "viewer": "مشاهد",
}

CLIENT_TYPES = {"individual": "فرد", "company": "شركة"}
CASE_STATUSES = {
    "new": "جديدة",
    "open": "مفتوحة",
    "in_progress": "قيد العمل",
    "waiting": "بانتظار إجراء",
    "court_session": "جلسة محكمة",
    "closed": "مغلقة",
    "archived": "مؤرشفة",
}
PRIORITIES = {"low": "منخفضة", "medium": "متوسطة", "high": "عالية", "urgent": "عاجلة"}
SESSION_STATUSES = {
    "scheduled": "مجدولة",
    "completed": "مكتملة",
    "postponed": "مؤجلة",
    "cancelled": "ملغاة",
}
TASK_STATUSES = {
    "new": "جديدة",
    "pending": "معلقة",
    "in_progress": "قيد التنفيذ",
    "completed": "مكتملة",
    "overdue": "متأخرة",
    "cancelled": "ملغاة",
}
TASK_TYPES = {
    "collection": "تحصيل",
    "client_followup": "متابعة عميل",
    "session_followup": "متابعة جلسة",
    "document_preparation": "تجهيز مستندات",
    "contract_review": "مراجعة عقد",
    "internal_reminder": "تذكير داخلي",
    "judgment_followup": "متابعة حكم",
    "execution_followup": "متابعة تنفيذ",
    "invoice_followup": "متابعة فاتورة",
}
INVOICE_STATUSES = {
    "draft": "مسودة",
    "unpaid": "غير مدفوعة",
    "partially_paid": "مدفوعة جزئياً",
    "paid": "مدفوعة",
    "cancelled": "ملغاة",
}
PAYMENT_METHODS = {
    "cash": "نقداً",
    "bank_transfer": "تحويل بنكي",
    "card": "بطاقة",
    "cheque": "شيك",
    "other": "أخرى",
}
CONSULTATION_STATUSES = {
    "new": "جديدة",
    "assigned": "مسندة",
    "in_progress": "قيد العمل",
    "completed": "مكتملة",
    "cancelled": "ملغاة",
}


def label(mapping: dict[str, str], key: str | None) -> str:
    if not key:
        return "-"
    return mapping.get(key, key)


def badge_class(value: str | None) -> str:
    if value in {"completed", "paid", "closed"}:
        return "badge-green"
    if value in {"urgent", "unpaid", "cancelled", "overdue"}:
        return "badge-red"
    if value in {"high", "waiting", "partially_paid", "postponed"}:
        return "badge-yellow"
    return "badge-blue"

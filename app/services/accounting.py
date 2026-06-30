from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    CaseFee,
    ChartAccount,
    Expense,
    FixedMonthlyExpense,
    FinancialAccount,
    Installment,
    Invoice,
    JournalEntry,
    Payment,
    PaymentVoucher,
    ReceiptVoucher,
)

DATE_STATUS_OPTIONS = {
    "confirmed": "تاريخ مؤكد",
    "estimated": "تاريخ تقديري",
    "unknown": "تاريخ غير معروف",
}
DATE_STATUS_BADGES = {
    "confirmed": "badge-green",
    "estimated": "badge-orange",
    "unknown": "badge-red",
}
DATE_STATUS_FILTERS = {
    "all": "عرض الكل",
    "confirmed": "عرض التواريخ المؤكدة فقط",
    "estimated": "عرض التواريخ التقديرية",
    "unknown": "عرض المدفوعات غير المؤرخة",
}
HISTORICAL_DATE_NOTE = "تاريخ تقديري - تم إدخالها من ملفات مالية قديمة بدون تاريخ دفع مؤكد"
UNKNOWN_DATE_NOTE = "تسوية مالية افتتاحية / مدفوعات تاريخية غير مؤرخة"
UNKNOWN_DATE_PLACEHOLDER = date(1900, 1, 1)
OLD_UNDATED_PAYMENT_LABEL = "مدفوعات قديمة غير مؤرخة"
OPENING_BALANCE_LABEL = "رصيد افتتاحي"

EXPENSE_CATEGORIES = [
    "رواتب",
    "إيجار",
    "كهرباء وماء",
    "إنترنت واتصالات",
    "رسوم حكومية",
    "رسوم محاكم",
    "مصاريف تنقل",
    "قرطاسية",
    "تسويق",
    "اشتراكات وبرامج",
    "مصروفات أخرى",
]

PAYMENT_METHODS_ACCOUNTING = {
    "cash": "نقد",
    "bank_transfer": "تحويل بنكي",
    "card": "بطاقة",
    "cheque": "شيك",
}

FIXED_EXPENSE_PAYMENT_METHODS = {
    **PAYMENT_METHODS_ACCOUNTING,
    "auto_debit": "خصم تلقائي",
}

CASE_FEE_PAYMENT_PLANS = {
    "one_time": "دفعة واحدة",
    "installments": "أقساط",
    "advance_judgment": "مقدم والباقي عند الحكم",
    "success_fee": "الدفع عند الفوز",
    "advance_success_fee": "مقدم والباقي نسبة عند الفوز",
}

CASE_FEE_STATUSES = {
    "paid": "مدفوع",
    "partial": "مدفوع جزئياً",
    "unpaid": "مستحق غير مدفوع",
    "overdue": "متأخر",
    "contingent": "معلق بشرط",
    "cancelled": "ملغي",
}

APPROVAL_LIMIT = Decimal("1000.00")
FIXED_EXPENSE_CATEGORIES = [
    "إيجار المكتب",
    "رواتب الموظفين",
    "اشتراكات الأنظمة",
    "الإنترنت والاتصالات",
    "الكهرباء والماء",
    "رسوم حكومية أو تراخيص",
    "خدمات محاسبية",
    "تنظيف وضيافة",
    "أخرى",
]
SALARY_FIXED_EXPENSE_KEYWORDS = ("رواتب", "راتب", "أجور", "اجور")

PAID_STATUSES = {"paid", "completed"}
FINANCIAL_OPEN_STATUSES = {"unpaid", "partially_paid", "partial", "pending", "overdue", "sent"}


def next_number(db: Session, model, field_name: str, prefix: str) -> str:
    count = db.scalar(select(func.count(model.id))) or 0
    return f"{prefix}-{date.today().year}-{count + 1:05d}"


def money(value) -> Decimal:
    return Decimal(str(value or 0))


def normalize_date_status(value: str | None) -> str:
    value = (value or "confirmed").strip()
    return value if value in DATE_STATUS_OPTIONS else "confirmed"


def date_status_badge(value: str | None) -> str:
    return DATE_STATUS_BADGES.get(normalize_date_status(value), "badge-blue")


def validate_date_quality(date_status: str | None, date_note: str | None, payment_date: date | None) -> tuple[str, str | None, date]:
    status = normalize_date_status(date_status)
    note = (date_note or "").strip()
    if status == "confirmed":
        if not payment_date:
            raise ValueError("تاريخ الدفع الحقيقي مطلوب عند اختيار تاريخ مؤكد.")
        return status, note or None, payment_date
    if status == "estimated":
        if not payment_date:
            raise ValueError("أدخل التاريخ التقديري أو نهاية الشهر المعروف.")
        if not note:
            raise ValueError("ملاحظة سبب التقدير مطلوبة عند اختيار تاريخ تقديري.")
        return status, note, payment_date
    return status, note or UNKNOWN_DATE_NOTE, UNKNOWN_DATE_PLACEHOLDER


def date_quality_counts(db: Session, start_date: date | None = None, end_date: date | None = None) -> dict:
    statuses = {
        key: {"label": label, "badge": DATE_STATUS_BADGES[key], "revenue": Decimal("0"), "expenses": Decimal("0"), "count": 0}
        for key, label in DATE_STATUS_OPTIONS.items()
    }

    def add_rows(model, date_column, amount_column, kind: str, *conditions) -> None:
        stmt = select(model.date_status, func.coalesce(func.sum(amount_column), 0), func.count(model.id)).where(*conditions)
        if start_date:
            stmt = stmt.where(date_column >= start_date)
        if end_date:
            stmt = stmt.where(date_column <= end_date)
        stmt = stmt.group_by(model.date_status)
        for status, total, count in db.execute(stmt).all():
            key = normalize_date_status(status)
            statuses[key][kind] += money(total)
            statuses[key]["count"] += count or 0

    add_rows(Payment, Payment.payment_date, Payment.amount, "revenue")
    add_rows(ReceiptVoucher, ReceiptVoucher.received_at, ReceiptVoucher.amount, "revenue", ReceiptVoucher.status == "active")
    add_rows(Expense, Expense.expense_date, Expense.amount, "expenses", Expense.status == "active")
    add_rows(PaymentVoucher, PaymentVoucher.paid_at, PaymentVoucher.amount, "expenses", PaymentVoucher.status == "active")
    for row in statuses.values():
        row["net"] = row["revenue"] - row["expenses"]
    return {
        "statuses": statuses,
        "has_uncertain": statuses["estimated"]["count"] > 0 or statuses["unknown"]["count"] > 0,
    }


def historical_date_review_rows(db: Session) -> list[dict]:
    rows: list[dict] = []

    def add(row: dict) -> None:
        rows.append(row)

    for payment in db.scalars(select(Payment).where(Payment.date_status.in_(["estimated", "unknown"]))).all():
        invoice = payment.invoice
        add(
            {
                "kind": "دفعة فاتورة",
                "number": invoice.invoice_number if invoice else f"#{payment.id}",
                "client": invoice.client.full_name if invoice and invoice.client else "-",
                "date": payment.payment_date,
                "amount": payment.amount,
                "date_status": payment.date_status,
                "date_note": payment.date_note,
                "url": f"/invoices/{payment.invoice_id}" if payment.invoice_id else "",
            }
        )
    for receipt in db.scalars(select(ReceiptVoucher).where(ReceiptVoucher.date_status.in_(["estimated", "unknown"]))).all():
        add(
            {
                "kind": "سند قبض",
                "number": receipt.receipt_number,
                "client": receipt.client.full_name if receipt.client else "-",
                "date": receipt.received_at,
                "amount": receipt.amount,
                "date_status": receipt.date_status,
                "date_note": receipt.date_note,
                "url": f"/accounting/receipts/{receipt.id}/print",
            }
        )
    for expense in db.scalars(select(Expense).where(Expense.date_status.in_(["estimated", "unknown"]))).all():
        add(
            {
                "kind": "مصروف",
                "number": expense.category,
                "client": expense.matter.case_number if expense.matter else "عام",
                "date": expense.expense_date,
                "amount": expense.amount,
                "date_status": expense.date_status,
                "date_note": expense.date_note,
                "url": "",
            }
        )
    for voucher in db.scalars(select(PaymentVoucher).where(PaymentVoucher.date_status.in_(["estimated", "unknown"]))).all():
        add(
            {
                "kind": "سند صرف",
                "number": voucher.voucher_number,
                "client": voucher.client.full_name if voucher.client else "عام",
                "date": voucher.paid_at,
                "amount": voucher.amount,
                "date_status": voucher.date_status,
                "date_note": voucher.date_note,
                "url": "",
            }
        )
    for entry in db.scalars(select(JournalEntry).where(JournalEntry.date_status.in_(["estimated", "unknown"]))).all():
        add(
            {
                "kind": "قيد يومي",
                "number": entry.entry_number,
                "client": entry.description,
                "date": entry.entry_date,
                "amount": entry.amount,
                "date_status": entry.date_status,
                "date_note": entry.date_note,
                "url": "/accounting/journal",
            }
        )
    rows.sort(key=lambda row: (row["date_status"], row["date"]), reverse=True)
    return rows


def calculate_balance(total_amount, paid_amount) -> Decimal:
    return max(money(total_amount) - money(paid_amount), Decimal("0"))


def calculate_days_overdue(due_date: date | None, today: date | None = None) -> int:
    if not due_date:
        return 0
    current_day = today or date.today()
    return max((current_day - due_date).days, 0)


def overdue_risk(days_overdue: int) -> dict[str, str]:
    if days_overdue > 30:
        return {"key": "high", "label": "متعثر عالي الخطورة", "badge": "badge-red"}
    if days_overdue >= 8:
        return {"key": "medium", "label": "متأخر متوسط", "badge": "badge-orange"}
    if days_overdue >= 1:
        return {"key": "simple", "label": "متأخر بسيط", "badge": "badge-yellow"}
    return {"key": "current", "label": "غير متعثر", "badge": "badge-blue"}


def _is_unsettled(status: str | None, balance: Decimal) -> bool:
    normalized = (status or "").strip().lower()
    return balance > 0 or normalized not in PAID_STATUSES


def _matches_overdue_filters(row: dict, filters: dict) -> bool:
    query = (filters.get("q") or "").strip().lower()
    if query:
        client_name = (row["client_name"] or "").lower()
        phone = (row["phone"] or "").lower()
        if query not in client_name and query not in phone:
            return False

    delay_bucket = filters.get("delay_bucket") or ""
    if delay_bucket and row["risk_key"] != delay_bucket:
        return False

    lawyer_id = filters.get("lawyer_id")
    if lawyer_id and row["lawyer_id"] != lawyer_id:
        return False

    matter_id = filters.get("matter_id")
    if matter_id and row["matter_id"] != matter_id:
        return False

    min_balance = filters.get("min_balance")
    if min_balance is not None and row["balance"] < min_balance:
        return False

    max_balance = filters.get("max_balance")
    if max_balance is not None and row["balance"] > max_balance:
        return False

    overdue_only = filters.get("overdue_only", True)
    if overdue_only and row["days_overdue"] <= 0:
        return False

    return True


def _overdue_row(
    *,
    source_type: str,
    source_id: int,
    number: str,
    client,
    matter,
    total_amount,
    paid_amount,
    due_date: date | None,
    status: str | None,
    today: date,
) -> dict | None:
    balance = calculate_balance(total_amount, paid_amount)
    if not due_date or not _is_unsettled(status, balance):
        return None
    days_overdue = calculate_days_overdue(due_date, today)
    risk = overdue_risk(days_overdue)
    return {
        "source_type": source_type,
        "source_id": source_id,
        "number": number,
        "client": client,
        "client_id": client.id if client else None,
        "client_name": client.full_name if client else "-",
        "phone": client.phone if client else "",
        "matter": matter,
        "matter_id": matter.id if matter else None,
        "matter_name": matter.title if matter else "-",
        "lawyer_id": matter.assigned_lawyer_id if matter else None,
        "total_amount": money(total_amount),
        "paid_amount": money(paid_amount),
        "balance": balance,
        "due_date": due_date,
        "days_overdue": days_overdue,
        "risk_key": risk["key"],
        "risk_label": risk["label"],
        "risk_badge": risk["badge"],
        "status": status or "",
        "detail_url": f"/invoices/{source_id}" if source_type == "invoice" else "/accounting/installments",
        "detail_label": "عرض الفاتورة" if source_type == "invoice" else "عرض القسط",
    }


def overdue_clients_report(db: Session, filters: dict | None = None, today: date | None = None) -> dict:
    filters = filters or {}
    current_day = today or date.today()
    rows: list[dict] = []

    invoice_stmt = (
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.matter))
        .where(Invoice.status != "cancelled")
        .order_by(Invoice.due_date.asc(), Invoice.id.desc())
    )
    if filters.get("overdue_only", True):
        invoice_stmt = invoice_stmt.where(Invoice.due_date < current_day)
    for invoice in db.scalars(invoice_stmt).all():
        row = _overdue_row(
            source_type="invoice",
            source_id=invoice.id,
            number=invoice.invoice_number,
            client=invoice.client,
            matter=invoice.matter,
            total_amount=invoice.total_amount,
            paid_amount=invoice.paid_amount,
            due_date=invoice.due_date,
            status=invoice.status,
            today=current_day,
        )
        if row and _matches_overdue_filters(row, filters):
            rows.append(row)

    installment_stmt = (
        select(Installment)
        .options(selectinload(Installment.client), selectinload(Installment.matter))
        .order_by(Installment.due_date.asc(), Installment.id.desc())
    )
    if filters.get("overdue_only", True):
        installment_stmt = installment_stmt.where(Installment.due_date < current_day)
    for installment in db.scalars(installment_stmt).all():
        row = _overdue_row(
            source_type="installment",
            source_id=installment.id,
            number=f"قسط #{installment.id}",
            client=installment.client,
            matter=installment.matter,
            total_amount=installment.amount,
            paid_amount=installment.paid_amount,
            due_date=installment.due_date,
            status=installment.status,
            today=current_day,
        )
        if row and _matches_overdue_filters(row, filters):
            rows.append(row)

    rows.sort(key=lambda item: (item["days_overdue"], item["balance"]), reverse=True)
    overdue_rows = [row for row in rows if row["days_overdue"] > 0]
    client_totals: dict[int, dict] = {}
    for row in overdue_rows:
        client_id = row["client_id"]
        if client_id is None:
            continue
        client_totals.setdefault(
            client_id,
            {"client": row["client"], "client_name": row["client_name"], "phone": row["phone"], "balance": Decimal("0")},
        )
        client_totals[client_id]["balance"] += row["balance"]

    top_clients = sorted(client_totals.values(), key=lambda item: item["balance"], reverse=True)[:5]
    return {
        "rows": rows,
        "summary": {
            "overdue_clients_count": len(client_totals),
            "total_overdue_balance": sum((row["balance"] for row in overdue_rows), Decimal("0")),
            "overdue_items_count": len(overdue_rows),
            "top_clients": top_clients,
        },
    }


def accounting_summary(db: Session, start_date: date | None = None, end_date: date | None = None) -> dict:
    invoice_stmt = select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(Invoice.status != "cancelled")
    payment_stmt = select(func.coalesce(func.sum(Payment.amount), 0))
    receipt_stmt = select(func.coalesce(func.sum(ReceiptVoucher.amount), 0)).where(ReceiptVoucher.status == "active")
    expense_stmt = select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.status == "active")
    voucher_stmt = select(func.coalesce(func.sum(PaymentVoucher.amount), 0)).where(PaymentVoucher.status == "active")
    if start_date:
        invoice_stmt = invoice_stmt.where(Invoice.issue_date >= start_date)
        payment_stmt = payment_stmt.where(Payment.payment_date >= start_date)
        receipt_stmt = receipt_stmt.where(ReceiptVoucher.received_at >= start_date)
        expense_stmt = expense_stmt.where(Expense.expense_date >= start_date)
        voucher_stmt = voucher_stmt.where(PaymentVoucher.paid_at >= start_date)
    if end_date:
        invoice_stmt = invoice_stmt.where(Invoice.issue_date <= end_date)
        payment_stmt = payment_stmt.where(Payment.payment_date <= end_date)
        receipt_stmt = receipt_stmt.where(ReceiptVoucher.received_at <= end_date)
        expense_stmt = expense_stmt.where(Expense.expense_date <= end_date)
        voucher_stmt = voucher_stmt.where(PaymentVoucher.paid_at <= end_date)
    revenue = money(db.scalar(payment_stmt)) + money(db.scalar(receipt_stmt))
    expenses = money(db.scalar(expense_stmt)) + money(db.scalar(voucher_stmt))
    contingent_stmt = select(func.count(CaseFee.id)).where(CaseFee.payment_plan.in_(["success_fee", "advance_success_fee", "advance_judgment"]), CaseFee.status == "contingent", CaseFee.is_cancelled.is_(False), CaseFee.is_group_primary.is_(True))
    return {
        "billed": money(db.scalar(invoice_stmt)),
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": revenue - expenses,
        "date_quality": date_quality_counts(db, start_date, end_date),
        "outstanding": money(db.scalar(select(func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0)).where(Invoice.status.in_(["unpaid", "partially_paid", "overdue", "sent"])))),
        "overdue_invoices": db.scalar(select(func.count(Invoice.id)).where(Invoice.due_date < date.today(), Invoice.status.in_(["unpaid", "partially_paid", "overdue", "sent"]))) or 0,
        "today_payments": money(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.payment_date == date.today()))),
        "contingent_fees": db.scalar(contingent_stmt) or 0,
    }


def current_month_range(today: date | None = None) -> tuple[date, date]:
    current_day = today or date.today()
    start = current_day.replace(day=1)
    end = current_day.replace(day=monthrange(current_day.year, current_day.month)[1])
    return start, end


def is_salary_fixed_expense(item: FixedMonthlyExpense) -> bool:
    text = f"{item.title or ''} {item.category or ''}"
    return any(keyword in text for keyword in SALARY_FIXED_EXPENSE_KEYWORDS)


def fixed_monthly_expense_components(db: Session, today: date | None = None) -> dict:
    active_expenses = db.scalars(
        select(FixedMonthlyExpense).where(FixedMonthlyExpense.is_active.is_(True))
    ).all()
    registered_salary_total = sum(
        (money(item.amount) for item in active_expenses if is_salary_fixed_expense(item)),
        Decimal("0"),
    )
    non_salary_total = sum(
        (money(item.amount) for item in active_expenses if not is_salary_fixed_expense(item)),
        Decimal("0"),
    )
    actual_salary_total = Decimal("0")
    salary_total = registered_salary_total
    return {
        "non_salary_total": non_salary_total,
        "registered_salary_total": registered_salary_total,
        "actual_salary_total": actual_salary_total,
        "salary_total": salary_total,
        "monthly_total": non_salary_total + salary_total,
        "active_expenses": active_expenses,
    }


def next_fixed_expense_due(expenses: list[FixedMonthlyExpense], today: date | None = None) -> dict | None:
    active = [item for item in expenses if item.is_active]
    if not active:
        return None
    current_day = today or date.today()
    days_in_month = monthrange(current_day.year, current_day.month)[1]
    candidates = []
    for item in active:
        due_day = min(max(item.due_day or 1, 1), days_in_month)
        due_date = current_day.replace(day=due_day)
        if due_date < current_day:
            next_month_year = current_day.year + (1 if current_day.month == 12 else 0)
            next_month = 1 if current_day.month == 12 else current_day.month + 1
            next_days = monthrange(next_month_year, next_month)[1]
            due_date = date(next_month_year, next_month, min(max(item.due_day or 1, 1), next_days))
        candidates.append({"expense": item, "due_date": due_date, "days_remaining": (due_date - current_day).days})
    return min(candidates, key=lambda item: item["due_date"])


def fixed_monthly_expense_summary(db: Session, today: date | None = None) -> dict:
    current_day = today or date.today()
    expenses = db.scalars(select(FixedMonthlyExpense).order_by(FixedMonthlyExpense.due_day, FixedMonthlyExpense.title)).all()
    active_expenses = [item for item in expenses if item.is_active]
    components = fixed_monthly_expense_components(db, current_day)
    monthly_total = components["monthly_total"]
    month_start, month_end = current_month_range(current_day)
    monthly_revenue = accounting_summary(db, month_start, month_end)["revenue"]
    days_in_month = monthrange(current_day.year, current_day.month)[1]
    return {
        "monthly_total": monthly_total,
        "active_count": len(active_expenses),
        "non_salary_total": components["non_salary_total"],
        "salary_total": components["salary_total"],
        "actual_salary_total": components["actual_salary_total"],
        "registered_salary_total": components["registered_salary_total"],
        "annual_total": monthly_total * Decimal("12"),
        "next_due": next_fixed_expense_due(expenses, current_day),
        "monthly_revenue": monthly_revenue,
        "estimated_net_profit": monthly_revenue - monthly_total,
        "break_even_monthly": monthly_total,
        "daily_needed": (monthly_total / Decimal(days_in_month)).quantize(Decimal("0.01")) if days_in_month else Decimal("0"),
    }


def financial_alerts(db: Session) -> list[str]:
    alerts: list[str] = []
    overdue_invoices = db.scalar(select(func.count(Invoice.id)).where(Invoice.due_date < date.today(), Invoice.status.in_(["unpaid", "partially_paid", "overdue", "sent"]))) or 0
    overdue_installments = db.scalar(select(func.count(Installment.id)).where(Installment.due_date < date.today(), Installment.status.in_(["pending", "overdue"]))) or 0
    pending_approvals = db.scalar(select(func.count(PaymentVoucher.id)).where(PaymentVoucher.approval_status == "pending")) or 0
    low_cash = db.scalar(select(func.count(FinancialAccount.id)).where(FinancialAccount.account_type == "cash", FinancialAccount.current_balance < 100)) or 0
    if overdue_invoices:
        alerts.append(f"يوجد {overdue_invoices} فاتورة متأخرة.")
    if overdue_installments:
        alerts.append(f"يوجد {overdue_installments} قسط متأخر.")
    if pending_approvals:
        alerts.append(f"يوجد {pending_approvals} سند صرف يحتاج اعتماد المدير.")
    if low_cash:
        alerts.append("رصيد الصندوق النقدي منخفض.")
    return alerts


def seed_accounting_defaults(db: Session) -> None:
    accounts = [
        ("1000", "الأصول", "asset", None),
        ("1100", "النقدية والبنوك", "asset", "1000"),
        ("1110", "الصندوق الرئيسي", "asset", "1100"),
        ("1120", "الحساب البنكي الرئيسي", "asset", "1100"),
        ("1130", "حسابات بنكية فرعية", "asset", "1100"),
        ("1140", "شيكات تحت التحصيل", "asset", "1100"),
        ("1150", "بوابات الدفع الإلكتروني", "asset", "1100"),
        ("1200", "الذمم المدينة", "asset", "1000"),
        ("1210", "ذمم العملاء - فواتير أتعاب", "asset", "1200"),
        ("1220", "إيرادات مستحقة غير مفوترة", "asset", "1200"),
        ("1230", "أقساط العملاء المستحقة", "asset", "1200"),
        ("1240", "سندات قبض قيد التسوية", "asset", "1200"),
        ("1250", "مخصص ديون مشكوك في تحصيلها", "contra_asset", "1200"),
        ("1300", "المصروفات المدفوعة مقدماً", "asset", "1000"),
        ("1310", "إيجار مدفوع مقدماً", "asset", "1300"),
        ("1320", "تأمين مدفوع مقدماً", "asset", "1300"),
        ("1330", "اشتراكات وبرامج مدفوعة مقدماً", "asset", "1300"),
        ("1340", "تراخيص مهنية مدفوعة مقدماً", "asset", "1300"),
        ("1400", "عهد ومبالغ قابلة للاسترداد من العملاء", "asset", "1000"),
        ("1410", "رسوم محاكم مدفوعة نيابة عن العملاء", "asset", "1400"),
        ("1420", "رسوم خبراء ومحكمين قابلة للاسترداد", "asset", "1400"),
        ("1430", "رسوم إعلان وترجمة وتوثيق قابلة للاسترداد", "asset", "1400"),
        ("1440", "مصاريف سفر وتنقل قابلة للاسترداد", "asset", "1400"),
        ("1500", "الأصول الثابتة", "asset", "1000"),
        ("1510", "أثاث وتجهيزات مكتبية", "asset", "1500"),
        ("1520", "أجهزة حاسب وطابعات", "asset", "1500"),
        ("1530", "أنظمة وبرامج مملوكة", "asset", "1500"),
        ("1540", "مكتبة قانونية ومراجع", "asset", "1500"),
        ("1590", "مجمع الإهلاك", "contra_asset", "1500"),
        ("1600", "ودائع وتأمينات", "asset", "1000"),
        ("1610", "تأمين إيجار المكتب", "asset", "1600"),
        ("1620", "ودائع خدمات", "asset", "1600"),
        ("2000", "الالتزامات", "liability", None),
        ("2100", "الموردون والمستحقات", "liability", "2000"),
        ("2110", "ذمم الموردين", "liability", "2100"),
        ("2120", "مصروفات مستحقة", "liability", "2100"),
        ("2130", "أتعاب مهنية مستحقة", "liability", "2100"),
        ("2140", "رواتب وأجور مستحقة", "liability", "2100"),
        ("2150", "إجازات ومكافآت نهاية خدمة مستحقة", "liability", "2100"),
        ("2200", "التزامات ضريبية ورسوم", "liability", "2000"),
        ("2210", "ضريبة القيمة المضافة مستحقة", "liability", "2200"),
        ("2220", "ضريبة دخل أو استقطاع مستحقة", "liability", "2200"),
        ("2230", "رسوم حكومية مستحقة", "liability", "2200"),
        ("2300", "أموال وأمانات العملاء", "liability", "2000"),
        ("2310", "دفعات مقدمة من العملاء", "liability", "2300"),
        ("2320", "أمانات عملاء محتفظ بها", "liability", "2300"),
        ("2330", "مبالغ محصلة نيابة عن العملاء", "liability", "2300"),
        ("2340", "إيرادات مؤجلة", "liability", "2300"),
        ("2400", "قروض وتمويل", "liability", "2000"),
        ("2410", "قروض قصيرة الأجل", "liability", "2400"),
        ("2420", "قروض طويلة الأجل", "liability", "2400"),
        ("3000", "الإيرادات", "revenue", None),
        ("3100", "أتعاب المحاماة", "revenue", "3000"),
        ("3110", "أتعاب استشارات قانونية", "revenue", "3100"),
        ("3120", "أتعاب تمثيل أمام المحاكم", "revenue", "3100"),
        ("3130", "أتعاب صياغة عقود", "revenue", "3100"),
        ("3140", "أتعاب تحكيم وتسوية", "revenue", "3100"),
        ("3150", "أتعاب تحصيل وتنفيذ", "revenue", "3100"),
        ("3160", "أتعاب شهرية Retainer", "revenue", "3100"),
        ("3170", "أتعاب دفع عند الفوز محققة", "revenue", "3100"),
        ("3200", "إيرادات الاستشارات", "revenue", "3000"),
        ("3210", "استشارات مكتبية", "revenue", "3200"),
        ("3220", "استشارات عن بعد", "revenue", "3200"),
        ("3300", "إيرادات العقود", "revenue", "3000"),
        ("3310", "مراجعة وصياغة عقود", "revenue", "3300"),
        ("3400", "إيرادات مستردات مصاريف عملاء", "revenue", "3000"),
        ("3410", "استرداد رسوم محاكم", "revenue", "3400"),
        ("3420", "استرداد رسوم خبراء وترجمة", "revenue", "3400"),
        ("3500", "خصومات ومردودات الإيرادات", "contra_revenue", "3000"),
        ("4000", "المصروفات التشغيلية", "expense", None),
        ("4100", "الرواتب", "expense", "4000"),
        ("4110", "رواتب المحامين", "expense", "4100"),
        ("4120", "رواتب الإداريين", "expense", "4100"),
        ("4130", "بدلات ومزايا", "expense", "4100"),
        ("4140", "تأمينات اجتماعية", "expense", "4100"),
        ("4150", "تدريب وتطوير مهني", "expense", "4100"),
        ("4200", "رسوم المحاكم غير المستردة", "expense", "4000"),
        ("4210", "رسوم قيد دعاوى غير مستردة", "expense", "4200"),
        ("4220", "رسوم خبراء غير مستردة", "expense", "4200"),
        ("4230", "رسوم إعلان وتوثيق غير مستردة", "expense", "4200"),
        ("4300", "مصروفات القضايا", "expense", "4000"),
        ("4310", "انتقالات للقضايا", "expense", "4300"),
        ("4320", "نسخ وطباعة ملفات", "expense", "4300"),
        ("4330", "ترجمة قانونية", "expense", "4300"),
        ("4340", "أتعاب خبراء ومكاتب خارجية", "expense", "4300"),
        ("4400", "إيجار ومرافق", "expense", "4000"),
        ("4410", "إيجار المكتب", "expense", "4400"),
        ("4420", "كهرباء وماء", "expense", "4400"),
        ("4430", "إنترنت واتصالات", "expense", "4400"),
        ("4440", "صيانة ونظافة", "expense", "4400"),
        ("4500", "تقنية وأنظمة", "expense", "4000"),
        ("4510", "اشتراكات إدارة القضايا", "expense", "4500"),
        ("4520", "اشتراكات محاسبة وفوترة", "expense", "4500"),
        ("4530", "استضافة وموقع إلكتروني", "expense", "4500"),
        ("4540", "أمن معلومات ونسخ احتياطي", "expense", "4500"),
        ("4600", "تسويق وعلاقات", "expense", "4000"),
        ("4610", "إعلانات وتسويق رقمي", "expense", "4600"),
        ("4620", "فعاليات ومؤتمرات", "expense", "4600"),
        ("4630", "ضيافة عملاء", "expense", "4600"),
        ("4700", "مصروفات إدارية", "expense", "4000"),
        ("4710", "قرطاسية ومطبوعات", "expense", "4700"),
        ("4720", "بريد وشحن", "expense", "4700"),
        ("4730", "رسوم بنكية", "expense", "4700"),
        ("4740", "تأمينات", "expense", "4700"),
        ("4750", "تراخيص واشتراكات مهنية", "expense", "4700"),
        ("4800", "إهلاك ومخصصات", "expense", "4000"),
        ("4810", "إهلاك الأصول الثابتة", "expense", "4800"),
        ("4820", "مخصص ديون مشكوك في تحصيلها", "expense", "4800"),
        ("4900", "مصروفات أخرى", "expense", "4000"),
        ("4910", "غرامات ومخالفات غير قابلة للتحميل", "expense", "4900"),
        ("4920", "فروقات عملة", "expense", "4900"),
        ("5000", "حقوق الملكية", "equity", None),
        ("5100", "رأس المال", "equity", "5000"),
        ("5200", "مسحوبات المالك", "equity", "5000"),
        ("5300", "أرباح مبقاة", "equity", "5000"),
        ("5400", "نتيجة السنة الحالية", "equity", "5000"),
    ]
    existing = {account.code: account for account in db.scalars(select(ChartAccount)).all()}
    for code, name, kind, _parent_code in accounts:
        account = existing.get(code)
        if account:
            account.name = name
            account.account_type = kind
            account.is_active = True
        else:
            account = ChartAccount(code=code, name=name, account_type=kind, is_active=True)
            db.add(account)
            existing[code] = account
    db.flush()
    for code, _name, _kind, parent_code in accounts:
        account = existing[code]
        account.parent_id = existing[parent_code].id if parent_code else None
    if not db.scalar(select(FinancialAccount).where(FinancialAccount.account_name == "الصندوق النقدي")):
        db.add(FinancialAccount(account_name="الصندوق النقدي", account_type="cash", opening_balance=Decimal("0"), current_balance=Decimal("0"), is_active=True))
        db.add(FinancialAccount(account_name="الحساب البنكي الرئيسي", account_type="bank", opening_balance=Decimal("0"), current_balance=Decimal("0"), is_active=True))
    db.commit()

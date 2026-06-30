from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Client,
    Expense,
    Invoice,
    Matter,
    OwnerFinancialSetting,
    Payment,
    PaymentVoucher,
    ReceiptVoucher,
    User,
)
from app.services.accounting import date_quality_counts, fixed_monthly_expense_components


LEGAL_SERVICE_TYPES = [
    "استشارة قانونية",
    "صياغة عقود",
    "قضايا تجارية",
    "قضايا مدنية",
    "قضايا عمالية",
    "قضايا أحوال شخصية",
    "تحصيل مطالبات",
    "باقات الشركات الشهرية",
    "مذكرات قانونية",
    "تمثيل أمام المحاكم",
]

CLIENT_SOURCES = ["واتساب", "موقع", "إحالة", "زيارة مكتب", "إعلان"]
FIXED_EXPENSE_CATEGORIES = {"رواتب", "إيجار", "كهرباء وماء", "إنترنت واتصالات", "اشتراكات وبرامج"}

def money(value) -> Decimal:
    if value in (None, ""):
        value = 0
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0.00")
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _json_list(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return fallback
    return [str(item) for item in data if str(item).strip()] or fallback


def get_owner_settings(db: Session) -> OwnerFinancialSetting:
    settings = db.scalar(select(OwnerFinancialSetting).order_by(OwnerFinancialSetting.id).limit(1))
    if settings:
        return settings
    settings = OwnerFinancialSetting(
        monthly_fixed_expenses=Decimal("2000"),
        monthly_revenue_target=Decimal("12000"),
        monthly_profit_target=Decimal("5000"),
        default_profit_margin=Decimal("70"),
        collection_warning_threshold=Decimal("75"),
        expense_warning_threshold=Decimal("15"),
        expense_categories_json=json.dumps(
            ["رواتب", "إيجار", "كهرباء وماء", "إنترنت واتصالات", "رسوم حكومية", "رسوم محاكم", "تسويق", "اشتراكات وبرامج"],
            ensure_ascii=False,
        ),
        service_categories_json=json.dumps(LEGAL_SERVICE_TYPES, ensure_ascii=False),
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_owner_settings(db: Session, **values) -> OwnerFinancialSetting:
    settings = get_owner_settings(db)
    for key, value in values.items():
        if key in {"expense_categories_json", "service_categories_json"}:
            setattr(settings, key, json.dumps([item.strip() for item in value.splitlines() if item.strip()], ensure_ascii=False))
        elif hasattr(settings, key):
            setattr(settings, key, money(value))
    db.commit()
    db.refresh(settings)
    return settings


def period_bounds(period: str | None, start_date: date | None, end_date: date | None, today: date | None = None) -> tuple[date, date, str]:
    today = today or date.today()
    period = period or "month"
    if period == "today":
        return today, today, "اليوم"
    if period == "week":
        return today - timedelta(days=today.weekday()), today, "هذا الأسبوع"
    if period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, quarter_month, 1), today, "هذا الربع"
    if period == "year":
        return date(today.year, 1, 1), today, "هذه السنة"
    if period == "custom" and start_date and end_date:
        return start_date, end_date, "فترة مخصصة"
    return today.replace(day=1), today, "هذا الشهر"


def client_source(client: Client | None) -> str:
    if not client:
        return "غير محدد"
    return CLIENT_SOURCES[(client.id - 1) % len(CLIENT_SOURCES)]


def service_type(invoice: Invoice | None = None, matter: Matter | None = None) -> str:
    matter = matter or (invoice.matter if invoice else None)
    if not matter:
        return "استشارة قانونية"
    if matter.case_type == "تجاري":
        return "قضايا تجارية"
    if matter.case_type == "مدني":
        return "قضايا مدنية"
    if matter.case_type == "عمالي":
        return "قضايا عمالية"
    if matter.case_type == "أحوال شخصية":
        return "قضايا أحوال شخصية"
    return matter.case_type or "استشارة قانونية"


def collection_status(invoice: Invoice) -> str:
    remaining = money(invoice.total_amount) - money(invoice.paid_amount)
    if remaining <= 0 or invoice.status == "paid":
        return "محصل"
    if invoice.due_date and invoice.due_date < date.today():
        return "متأخر"
    return "غير محصل"


def _matches_filters(invoice: Invoice, filters: dict) -> bool:
    if filters.get("service_type") and service_type(invoice) != filters["service_type"]:
        return False
    if filters.get("lawyer_id") and invoice.matter and str(invoice.matter.assigned_lawyer_id or "") != str(filters["lawyer_id"]):
        return False
    if filters.get("lawyer_id") and not invoice.matter:
        return False
    if filters.get("collection_status") and collection_status(invoice) != filters["collection_status"]:
        return False
    if filters.get("client_source") and client_source(invoice.client) != filters["client_source"]:
        return False
    return True


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _month_label(value: date) -> str:
    return value.strftime("%m/%Y")


def _load_data(db: Session, start: date, end: date, filters: dict) -> dict:
    invoices = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.matter).selectinload(Matter.assigned_lawyer))
        .where(Invoice.issue_date.between(start, end), Invoice.status != "cancelled")
        .order_by(Invoice.issue_date.desc())
    ).all()
    invoices = [invoice for invoice in invoices if _matches_filters(invoice, filters)]
    invoice_ids = [invoice.id for invoice in invoices]

    payments = []
    if invoice_ids:
        payments = db.scalars(
            select(Payment).where(Payment.invoice_id.in_(invoice_ids), Payment.payment_date.between(start, end))
        ).all()

    receipts = db.scalars(
        select(ReceiptVoucher)
        .options(selectinload(ReceiptVoucher.client), selectinload(ReceiptVoucher.matter).selectinload(Matter.assigned_lawyer))
        .where(ReceiptVoucher.received_at.between(start, end), ReceiptVoucher.status == "active")
        .order_by(ReceiptVoucher.received_at.desc())
    ).all()
    receipts = [
        receipt
        for receipt in receipts
        if (not filters.get("service_type") or service_type(matter=receipt.matter) == filters["service_type"])
        and (not filters.get("lawyer_id") or (receipt.matter and str(receipt.matter.assigned_lawyer_id or "") == str(filters["lawyer_id"])))
        and (not filters.get("client_source") or client_source(receipt.client) == filters["client_source"])
    ]

    expenses = db.scalars(
        select(Expense)
        .options(selectinload(Expense.added_by), selectinload(Expense.matter))
        .where(Expense.expense_date.between(start, end), Expense.status == "active")
        .order_by(Expense.expense_date.desc())
    ).all()
    vouchers = db.scalars(
        select(PaymentVoucher)
        .options(selectinload(PaymentVoucher.created_by))
        .where(PaymentVoucher.paid_at.between(start, end), PaymentVoucher.status == "active")
        .order_by(PaymentVoucher.paid_at.desc())
    ).all()
    return {"invoices": invoices, "payments": payments, "receipts": receipts, "expenses": expenses, "vouchers": vouchers}


def build_owner_financial_report(db: Session, filters: dict | None = None) -> dict:
    filters = filters or {}
    settings = get_owner_settings(db)
    start, end, period_label = period_bounds(filters.get("period"), filters.get("start_date"), filters.get("end_date"))
    data = _load_data(db, start, end, filters)
    invoices = data["invoices"]
    payments = data["payments"]
    receipts = data["receipts"]
    expenses = data["expenses"]
    vouchers = data["vouchers"]

    total_revenue = money(sum((money(invoice.total_amount) for invoice in invoices), Decimal("0")))
    collected = money(sum((money(payment.amount) for payment in payments), Decimal("0"))) + money(
        sum((money(receipt.amount) for receipt in receipts), Decimal("0"))
    )
    outstanding = money(sum((money(invoice.total_amount) - money(invoice.paid_amount) for invoice in invoices), Decimal("0")))
    overdue_invoices = [invoice for invoice in invoices if collection_status(invoice) == "متأخر"]

    expense_rows = []
    for expense in expenses:
        kind = "ثابت" if expense.category in FIXED_EXPENSE_CATEGORIES else "متغير"
        expense_rows.append(
            {
                "date": expense.expense_date,
                "category": expense.category,
                "description": expense.notes or (expense.matter.title if expense.matter else "مصروف تشغيلي"),
                "amount": money(expense.amount),
                "kind": kind,
                "method": expense.payment_method,
                "created_by": expense.added_by.full_name if expense.added_by else "-",
                "attachment_url": expense.attachment_url,
                "date_status": expense.date_status,
                "date_note": expense.date_note,
            }
        )
    for voucher in vouchers:
        kind = "ثابت" if voucher.expense_type in FIXED_EXPENSE_CATEGORIES else "متغير"
        expense_rows.append(
            {
                "date": voucher.paid_at,
                "category": voucher.expense_type,
                "description": voucher.beneficiary,
                "amount": money(voucher.amount),
                "kind": kind,
                "method": voucher.payment_method,
                "created_by": voucher.created_by.full_name if voucher.created_by else "-",
                "attachment_url": voucher.attachment_url,
                "date_status": voucher.date_status,
                "date_note": voucher.date_note,
            }
        )
    total_expenses = money(sum((row["amount"] for row in expense_rows), Decimal("0")))
    fixed_components = fixed_monthly_expense_components(db)
    active_fixed_monthly_expenses = money(fixed_components["monthly_total"])
    fixed_expenses = active_fixed_monthly_expenses or money(sum((row["amount"] for row in expense_rows if row["kind"] == "ثابت"), Decimal("0"))) or money(settings.monthly_fixed_expenses)
    variable_expenses = money(sum((row["amount"] for row in expense_rows if row["kind"] == "متغير"), Decimal("0")))
    net_profit = total_revenue - total_expenses
    profit_margin = percent(net_profit, total_revenue)
    collection_rate = percent(collected, total_revenue)
    new_clients = len({invoice.client_id for invoice in invoices})
    open_cases = db.scalar(select(func.count(Matter.id)).where(Matter.status.in_(["new", "open", "in_progress", "waiting", "court_session"]))) or 0
    average_client_value = money(total_revenue / Decimal(new_clients)) if new_clients else Decimal("0.00")
    average_case_cost = money(total_expenses / Decimal(max(len(invoices), 1)))

    margin_ratio = (profit_margin / Decimal("100")) if profit_margin > 0 else (money(settings.default_profit_margin) / Decimal("100"))
    if margin_ratio <= 0:
        margin_ratio = Decimal("0.70")
    break_even_amount = money(fixed_expenses / margin_ratio)
    month_start = date.today().replace(day=1)
    month_data = _load_data(db, month_start, date.today(), {key: value for key, value in filters.items() if key not in {"period", "start_date", "end_date"}})
    current_month_revenue = money(sum((money(invoice.total_amount) for invoice in month_data["invoices"]), Decimal("0")))
    remaining_to_break_even = max(Decimal("0.00"), break_even_amount - current_month_revenue)
    break_even_progress = min(Decimal("100.00"), percent(current_month_revenue, break_even_amount))
    required_clients = ceil(remaining_to_break_even / average_client_value) if average_client_value > 0 and remaining_to_break_even > 0 else 0
    day_of_month = max(date.today().day, 1)
    daily_revenue_rate = current_month_revenue / Decimal(day_of_month)
    expected_break_even_date = None
    if remaining_to_break_even <= 0:
        expected_break_even_date = date.today()
    elif daily_revenue_rate > 0:
        expected_break_even_date = date.today() + timedelta(days=ceil(remaining_to_break_even / daily_revenue_rate))

    revenue_rows = [
        {
            "invoice_number": invoice.invoice_number,
            "client": invoice.client.full_name if invoice.client else "-",
            "service_type": service_type(invoice),
            "lawyer": invoice.matter.assigned_lawyer.full_name if invoice.matter and invoice.matter.assigned_lawyer else "-",
            "total_amount": money(invoice.total_amount),
            "paid_amount": money(invoice.paid_amount),
            "remaining": money(invoice.total_amount) - money(invoice.paid_amount),
            "due_date": invoice.due_date,
            "collection_status": collection_status(invoice),
            "client_source": client_source(invoice.client),
            "detail_url": f"/invoices/{invoice.id}",
        }
        for invoice in invoices
    ]

    service_groups = defaultdict(lambda: {"requests": 0, "revenue": Decimal("0.00")})
    for invoice in invoices:
        key = service_type(invoice)
        service_groups[key]["requests"] += 1
        service_groups[key]["revenue"] += money(invoice.total_amount)
    service_profitability = []
    for name, item in service_groups.items():
        share = item["revenue"] / total_revenue if total_revenue > 0 else Decimal("0")
        estimated_cost = money(variable_expenses * share)
        profit = money(item["revenue"] - estimated_cost)
        margin = percent(profit, item["revenue"])
        if margin >= 50:
            rating = "مربحة"
        elif margin >= 20:
            rating = "متوسطة"
        else:
            rating = "خاسرة"
        service_profitability.append(
            {
                "service": name,
                "requests": item["requests"],
                "revenue": money(item["revenue"]),
                "average_revenue": money(item["revenue"] / Decimal(item["requests"])) if item["requests"] else Decimal("0.00"),
                "estimated_cost": estimated_cost,
                "net_profit": profit,
                "profit_margin": margin,
                "rating": rating,
            }
        )
    service_profitability.sort(key=lambda row: row["net_profit"], reverse=True)

    total_due = outstanding
    overdue_total = money(sum((money(invoice.total_amount) - money(invoice.paid_amount) for invoice in overdue_invoices), Decimal("0")))
    top_overdue = sorted(revenue_rows, key=lambda row: row["remaining"], reverse=True)[:5]
    due_this_week = [row for row in revenue_rows if row["due_date"] and date.today() <= row["due_date"] <= date.today() + timedelta(days=7)]
    overdue_over_30 = [
        row
        for row in revenue_rows
        if row["due_date"] and row["collection_status"] == "متأخر" and row["due_date"] < date.today() - timedelta(days=30)
    ]

    month_days = calendar.monthrange(date.today().year, date.today().month)[1]
    projected_revenue = money(current_month_revenue / Decimal(day_of_month) * Decimal(month_days)) if day_of_month else current_month_revenue
    current_month_expenses = money(
        sum((row["amount"] for row in expense_rows if str(row["date"])[:7] == date.today().strftime("%Y-%m")), Decimal("0"))
    )
    projected_expenses = money(current_month_expenses / Decimal(day_of_month) * Decimal(month_days)) if day_of_month else current_month_expenses
    projected_profit = projected_revenue - projected_expenses
    extra_revenue_needed = max(Decimal("0.00"), break_even_amount - projected_revenue)
    extra_clients_needed = ceil(extra_revenue_needed / average_client_value) if average_client_value > 0 and extra_revenue_needed > 0 else 0
    forecast_recommendation = "حافظ على معدل التحصيل الحالي وركز على الخدمات الأعلى ربحاً."
    if projected_revenue < break_even_amount:
        forecast_recommendation = "المكتب يحتاج زيادة تحصيل أو مبيعات إضافية هذا الشهر للوصول إلى التعادل."
    elif collection_rate < money(settings.collection_warning_threshold):
        forecast_recommendation = "الإيراد جيد، لكن التحصيل يحتاج متابعة للفواتير المتأخرة."

    alerts = []
    if current_month_revenue < break_even_amount:
        alerts.append({"level": "warning", "text": "المكتب أقل من نقطة التعادل لهذا الشهر."})
    else:
        alerts.append({"level": "success", "text": "المكتب وصل إلى نقطة التعادل لهذا الشهر."})
    previous_month_start = (month_start - timedelta(days=1)).replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_expenses = money(
        sum((money(row.amount) for row in db.scalars(select(Expense).where(Expense.expense_date.between(previous_month_start, previous_month_end), Expense.status == "active")).all()), Decimal("0"))
    )
    if previous_expenses > 0 and current_month_expenses > previous_expenses * (Decimal("1") + money(settings.expense_warning_threshold) / Decimal("100")):
        alerts.append({"level": "danger", "text": "المصاريف زادت عن الشهر السابق."})
    if collection_rate < money(settings.collection_warning_threshold) and total_revenue > 0:
        alerts.append({"level": "danger", "text": "التحصيل أقل من الحد المطلوب."})
    if overdue_invoices:
        alerts.append({"level": "warning", "text": f"توجد {len(overdue_invoices)} فواتير متأخرة تحتاج متابعة."})
    for item in service_profitability:
        if item["rating"] == "خاسرة":
            alerts.append({"level": "danger", "text": f"خدمة {item['service']} تحقق خسارة تقديرية."})
            break
    if new_clients < 2:
        alerts.append({"level": "info", "text": "العملاء الجدد أقل من المطلوب للفترة الحالية."})
    if service_profitability:
        alerts.append({"level": "success", "text": f"أفضل خدمة ربحاً: {service_profitability[0]['service']}."})

    months = []
    cursor = (date.today().replace(day=1) - timedelta(days=150)).replace(day=1)
    for _ in range(6):
        months.append(cursor)
        year = cursor.year + (cursor.month // 12)
        month = 1 if cursor.month == 12 else cursor.month + 1
        cursor = date(year, month, 1)
    monthly_revenue = {_month_key(month): Decimal("0.00") for month in months}
    monthly_expenses = {_month_key(month): Decimal("0.00") for month in months}
    all_recent_invoices = db.scalars(select(Invoice).where(Invoice.issue_date >= months[0], Invoice.status != "cancelled")).all()
    for invoice in all_recent_invoices:
        monthly_revenue[_month_key(invoice.issue_date)] = monthly_revenue.get(_month_key(invoice.issue_date), Decimal("0.00")) + money(invoice.total_amount)
    for expense in db.scalars(select(Expense).where(Expense.expense_date >= months[0], Expense.status == "active")).all():
        monthly_expenses[_month_key(expense.expense_date)] = monthly_expenses.get(_month_key(expense.expense_date), Decimal("0.00")) + money(expense.amount)

    charts = {
        "months": [_month_label(month) for month in months],
        "monthly_revenue": [float(money(monthly_revenue[_month_key(month)])) for month in months],
        "monthly_expenses": [float(money(monthly_expenses[_month_key(month)])) for month in months],
        "monthly_profit": [float(money(monthly_revenue[_month_key(month)] - monthly_expenses[_month_key(month)])) for month in months],
        "service_labels": [item["service"] for item in service_profitability],
        "service_values": [float(item["revenue"]) for item in service_profitability],
        "expense_labels": list({row["category"] for row in expense_rows}) or ["لا توجد مصاريف"],
        "expense_values": [
            float(money(sum((row["amount"] for row in expense_rows if row["category"] == category), Decimal("0"))))
            for category in (list({row["category"] for row in expense_rows}) or ["لا توجد مصاريف"])
        ],
        "collection_labels": [row["invoice_number"] for row in revenue_rows[:8]],
        "collection_values": [float(row["paid_amount"]) for row in revenue_rows[:8]],
        "break_even_values": [float(current_month_revenue), float(max(Decimal("0.00"), break_even_amount - current_month_revenue))],
    }

    monthly_report = {
        "revenue_summary": total_revenue,
        "expense_summary": total_expenses,
        "net_profit": net_profit,
        "break_even_status": "تم الوصول" if remaining_to_break_even <= 0 else "لم يتم الوصول",
        "loss_reasons": ["ارتفاع المصاريف المتغيرة", "ضعف التحصيل"] if net_profit < 0 else [],
        "best_sources": sorted(CLIENT_SOURCES, key=lambda source: sum(row["total_amount"] for row in revenue_rows if row["client_source"] == source), reverse=True)[:3],
        "top_services": [item["service"] for item in service_profitability[:3]],
        "overdues": overdue_total,
        "recommendations": [forecast_recommendation, "راجع الخدمات منخفضة الهامش قبل قبول ملفات جديدة مشابهة."],
    }

    return {
        "settings": settings,
        "period": {"start": start, "end": end, "label": period_label},
        "filters": filters,
        "filter_options": {
            "service_types": _json_list(settings.service_categories_json, LEGAL_SERVICE_TYPES),
            "expense_categories": _json_list(settings.expense_categories_json, sorted(FIXED_EXPENSE_CATEGORIES)),
            "client_sources": CLIENT_SOURCES,
            "lawyers": db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(["admin", "lawyer"])).order_by(User.full_name)).all(),
        },
        "summary": {
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "profit_margin": profit_margin,
            "collected": collected,
            "outstanding": outstanding,
            "fixed_expenses": fixed_expenses,
            "variable_expenses": variable_expenses,
            "new_clients": new_clients,
            "open_cases": open_cases,
            "average_client_value": average_client_value,
            "average_case_cost": average_case_cost,
            "collection_rate": collection_rate,
            "overdue_invoices": len(overdue_invoices),
        },
        "break_even": {
            "fixed_monthly_expenses": fixed_expenses,
            "average_profit_margin": (margin_ratio * Decimal("100")).quantize(Decimal("0.01")),
            "monthly_break_even": break_even_amount,
            "current_month_revenue": current_month_revenue,
            "remaining": remaining_to_break_even,
            "progress": break_even_progress,
            "required_clients": required_clients,
            "expected_date": expected_break_even_date,
        },
        "alerts": alerts,
        "date_quality": date_quality_counts(db, start, end),
        "charts": charts,
        "revenues": revenue_rows,
        "expenses": expense_rows,
        "service_profitability": service_profitability,
        "collection": {
            "total_due": total_due,
            "overdue_total": overdue_total,
            "top_overdue": top_overdue,
            "due_this_week": due_this_week,
            "overdue_over_30": overdue_over_30,
            "collection_rate": collection_rate,
        },
        "forecast": {
            "projected_revenue": projected_revenue,
            "projected_expenses": projected_expenses,
            "projected_profit": projected_profit,
            "will_reach_break_even": projected_revenue >= break_even_amount,
            "extra_revenue_needed": extra_revenue_needed,
            "extra_clients_needed": extra_clients_needed,
            "recommendation": forecast_recommendation,
        },
        "monthly_report": monthly_report,
    }

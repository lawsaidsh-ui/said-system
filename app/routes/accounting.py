from datetime import date, datetime
from decimal import Decimal
from html import escape
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    CaseFee,
    ChartAccount,
    Client,
    Expense,
    FixedMonthlyExpense,
    FinancialAccount,
    Installment,
    Invoice,
    JournalEntry,
    Matter,
    Payment,
    PaymentVoucher,
    ReceiptVoucher,
    Task,
    User,
)
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date, parse_decimal, save_upload
from app.services.accounting import (
    APPROVAL_LIMIT,
    CASE_FEE_PAYMENT_PLANS,
    CASE_FEE_STATUSES,
    DATE_STATUS_FILTERS,
    DATE_STATUS_OPTIONS,
    EXPENSE_CATEGORIES,
    FIXED_EXPENSE_CATEGORIES,
    FIXED_EXPENSE_PAYMENT_METHODS,
    OLD_UNDATED_PAYMENT_LABEL,
    OPENING_BALANCE_LABEL,
    PAYMENT_METHODS_ACCOUNTING,
    accounting_summary,
    calculate_balance,
    date_quality_counts,
    date_status_badge,
    financial_alerts,
    fixed_monthly_expense_summary,
    historical_date_review_rows,
    next_number,
    money,
    normalize_date_status,
    overdue_clients_report,
    validate_date_quality,
)
from app.services.audit import log_action
from app.services.auth import ensure_role, get_current_user
from app.services.labels import CASE_STATUSES
from app.services.whatsapp import normalize_phone, whatsapp_url
from app.templating import templates

router = APIRouter(prefix="/accounting", tags=["accounting"])

RECEIPT_TYPES = {
    "case_fee": "أتعاب قضية",
    "invoice": "فاتورة",
    "general": "دفعة عامة",
}


def require_finance(user: User) -> None:
    ensure_role(user, {"accountant"})


def require_fixed_expense_view(user: User) -> None:
    ensure_role(user, {"accountant", "viewer"})


def require_fixed_expense_write(user: User) -> None:
    ensure_role(user, {"accountant"})


def validate_client_matter(db: Session, client_id: int | None, matter_id: str) -> int | None:
    parsed_matter_id = int_or_none(matter_id)
    if not parsed_matter_id:
        return None
    matter = db.get(Matter, parsed_matter_id)
    if not matter or not client_id or matter.client_id != client_id:
        raise HTTPException(status_code=400, detail="Selected matter does not belong to the selected client.")
    return parsed_matter_id


def validate_client_invoice(db: Session, client_id: int, invoice_id: str) -> int | None:
    parsed_invoice_id = int_or_none(invoice_id)
    if not parsed_invoice_id:
        return None
    invoice = db.get(Invoice, parsed_invoice_id)
    if not invoice or invoice.client_id != client_id:
        raise HTTPException(status_code=400, detail="Selected invoice does not belong to the selected client.")
    return parsed_invoice_id


def decimal_filter(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    return parse_decimal(value)


def missing_case_fees_stmt(q: str | None = None, status: str | None = None):
    has_active_fee = (
        select(CaseFee.id)
        .where(CaseFee.matter_id == Matter.id, CaseFee.is_cancelled.is_(False))
        .exists()
    )
    stmt = (
        select(Matter)
        .options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
        .where(~has_active_fee)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.join(Client).where(
            or_(
                Matter.case_number.ilike(like),
                Matter.ministry_case_number.ilike(like),
                Matter.title.ilike(like),
                Client.full_name.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Matter.status == status)
    return stmt


def case_fee_group_members(db: Session, fee: CaseFee) -> list[CaseFee]:
    if not fee.group_key:
        return [fee]
    return db.scalars(
        select(CaseFee)
        .options(selectinload(CaseFee.matter))
        .where(CaseFee.group_key == fee.group_key)
        .order_by(CaseFee.is_group_primary.desc(), CaseFee.id)
    ).all()


def case_fee_group_labels(fees: list[CaseFee]) -> dict[str, list[str]]:
    labels: dict[str, list[str]] = {}
    for fee in fees:
        if not fee.group_key or not fee.matter:
            continue
        labels.setdefault(fee.group_key, []).append(f"{fee.matter.case_number} - {fee.matter.title}")
    return labels


def primary_case_fee_for_matter(db: Session, matter_id: int) -> CaseFee | None:
    fee = db.scalar(
        select(CaseFee)
        .where(CaseFee.matter_id == matter_id, CaseFee.is_cancelled.is_(False))
        .order_by(CaseFee.is_group_primary.desc(), CaseFee.created_at.desc(), CaseFee.id.desc())
    )
    if fee and fee.group_key and not fee.is_group_primary:
        primary = db.scalar(
            select(CaseFee).where(
                CaseFee.group_key == fee.group_key,
                CaseFee.is_group_primary.is_(True),
                CaseFee.is_cancelled.is_(False),
            )
        )
        return primary or fee
    return fee


def apply_case_fee_receipt(db: Session, matter_id: int | None, amount: Decimal) -> CaseFee | None:
    if not matter_id:
        return None
    fee = primary_case_fee_for_matter(db, matter_id)
    if not fee or money(fee.fee_amount) <= 0:
        return None
    paid = money(fee.paid_amount)
    total = money(fee.fee_amount)
    remaining = calculate_balance(total, paid)
    if remaining <= 0 or fee.status == "paid":
        raise HTTPException(status_code=400, detail="أتعاب هذه القضية مدفوعة بالكامل، ولا يمكن تسجيل دفعة أخرى.")
    if amount > remaining:
        raise HTTPException(status_code=400, detail=f"المبلغ أكبر من المتبقي على أتعاب القضية. المتبقي: {remaining:.2f}")
    fee.paid_amount = paid + amount
    fee.status = "paid" if fee.paid_amount >= total else "partial"
    for member in case_fee_group_members(db, fee):
        if member.id == fee.id:
            continue
        member.status = fee.status
    return fee


def apply_invoice_receipt(db: Session, invoice: Invoice, amount: Decimal) -> None:
    remaining = money(invoice.total_amount) - money(invoice.paid_amount)
    if remaining <= 0 or invoice.status == "paid":
        raise HTTPException(status_code=400, detail="هذه الفاتورة مدفوعة بالكامل، ولا يمكن تسجيل سند قبض آخر عليها.")
    if amount > remaining:
        raise HTTPException(status_code=400, detail=f"المبلغ أكبر من المتبقي على الفاتورة. المتبقي: {remaining:.2f}")
    invoice.paid_amount = money(invoice.paid_amount) + amount
    invoice.status = "paid" if money(invoice.paid_amount) >= money(invoice.total_amount) else "partially_paid"
    if invoice.status == "paid":
        for task in db.scalars(select(Task).where(Task.invoice_id == invoice.id, Task.status != "completed")).all():
            task.status = "completed"
            task.completed_at = datetime.now()


def refresh_case_fee_status(fee: CaseFee) -> None:
    total = money(fee.fee_amount)
    paid = money(fee.paid_amount)
    if total <= 0 and fee.payment_plan in {"success_fee", "advance_success_fee", "advance_judgment"}:
        fee.status = "contingent"
    elif paid <= 0:
        fee.status = "unpaid"
    elif paid >= total:
        fee.status = "paid"
    else:
        fee.status = "partial"


def reverse_case_fee_receipt(db: Session, receipt: ReceiptVoucher) -> None:
    fee = receipt.case_fee or (primary_case_fee_for_matter(db, receipt.matter_id) if receipt.matter_id else None)
    if not fee:
        return
    fee.paid_amount = max(money(fee.paid_amount) - money(receipt.amount), Decimal("0"))
    refresh_case_fee_status(fee)
    for member in case_fee_group_members(db, fee):
        if member.id == fee.id:
            continue
        member.status = fee.status


def reverse_invoice_receipt(db: Session, receipt: ReceiptVoucher) -> None:
    if not receipt.invoice:
        return
    receipt.invoice.paid_amount = max(money(receipt.invoice.paid_amount) - money(receipt.amount), Decimal("0"))
    if receipt.invoice.paid_amount <= 0:
        receipt.invoice.status = "unpaid"
    elif receipt.invoice.paid_amount >= receipt.invoice.total_amount:
        receipt.invoice.status = "paid"
    else:
        receipt.invoice.status = "partially_paid"


def receipt_case_fee_for_display(db: Session, receipt: ReceiptVoucher) -> CaseFee | None:
    if (receipt.receipt_type or "case_fee") != "case_fee":
        return None
    if receipt.case_fee:
        return receipt.case_fee
    if receipt.matter_id:
        return primary_case_fee_for_matter(db, receipt.matter_id)
    return None


def receipt_case_fee_labels(db: Session, receipts: list[ReceiptVoucher]) -> dict[int, dict]:
    labels: dict[int, dict] = {}
    for receipt in receipts:
        fee = receipt_case_fee_for_display(db, receipt)
        if not fee:
            continue
        members = case_fee_group_members(db, fee)
        labels[receipt.id] = {
            "is_group": bool(fee.group_key and len(members) > 1),
            "count": len(members),
            "labels": [f"{member.matter.case_number} - {member.matter.title}" for member in members if member.matter],
            "remaining": calculate_balance(fee.fee_amount, fee.paid_amount),
        }
    return labels


def case_fee_payment_context(db: Session) -> dict[int, dict]:
    fees = db.scalars(
        select(CaseFee)
        .options(selectinload(CaseFee.matter))
        .where(CaseFee.is_cancelled.is_(False))
        .order_by(CaseFee.is_group_primary.desc(), CaseFee.id)
    ).all()
    by_group = {}
    for fee in fees:
        if fee.group_key:
            by_group.setdefault(fee.group_key, []).append(fee)
    context: dict[int, dict] = {}
    for fee in fees:
        primary = fee
        members = [fee]
        if fee.group_key:
            members = by_group.get(fee.group_key, [fee])
            primary = next((member for member in members if member.is_group_primary), fee)
        if not fee.matter_id:
            continue
        remaining = calculate_balance(primary.fee_amount, primary.paid_amount)
        context[fee.matter_id] = {
            "is_group": bool(primary.group_key and len(members) > 1),
            "count": len(members),
            "remaining": remaining,
            "paid": remaining <= 0 or primary.status == "paid",
            "label": f"{'أتعاب مشتركة' if primary.group_key and len(members) > 1 else 'أتعاب قضية واحدة'} - المتبقي {remaining:.2f}",
        }
    return context


def chart_account_by_code(db: Session, code: str) -> ChartAccount:
    account = db.scalar(select(ChartAccount).where(ChartAccount.code == code, ChartAccount.is_active.is_(True)))
    if not account:
        raise HTTPException(status_code=400, detail=f"الحساب المحاسبي {code} غير موجود أو غير مفعل.")
    return account


def create_paid_case_fee_journal(db: Session, *, case_fee: CaseFee, amount: Decimal, user: User, entry_date: date | None = None, date_status: str = "confirmed", date_note: str | None = None) -> JournalEntry | None:
    if amount <= 0:
        return None
    debit_account = chart_account_by_code(db, "1110")
    credit_code = "3170" if case_fee.payment_plan in {"success_fee", "advance_success_fee"} else "3120"
    credit_account = chart_account_by_code(db, credit_code)
    matter_label = case_fee.matter.case_number if case_fee.matter else f"#{case_fee.matter_id}"
    description = f"قيد تلقائي: تحصيل مبلغ مدفوع من أتعاب قضية - {matter_label}"
    entry = JournalEntry(
        entry_number=next_number(db, JournalEntry, "entry_number", "JE"),
        entry_date=entry_date or date.today(),
        date_status=date_status,
        date_note=date_note,
        description=description,
        debit_account_id=debit_account.id,
        credit_account_id=credit_account.id,
        amount=amount,
        created_by_id=user.id,
        status="posted",
    )
    db.add(entry)
    return entry


def create_case_fee_receipt_reversal_journal(db: Session, *, receipt: ReceiptVoucher, user: User) -> JournalEntry | None:
    fee = receipt.case_fee or (primary_case_fee_for_matter(db, receipt.matter_id) if receipt.matter_id else None)
    if not fee or money(receipt.amount) <= 0:
        return None
    debit_code = "3170" if fee.payment_plan in {"success_fee", "advance_success_fee"} else "3120"
    debit_account = chart_account_by_code(db, debit_code)
    credit_account = chart_account_by_code(db, "1110")
    entry = JournalEntry(
        entry_number=next_number(db, JournalEntry, "entry_number", "JE"),
        entry_date=date.today(),
        description=f"قيد عكسي: إلغاء سند قبض أتعاب قضية {receipt.receipt_number}",
        debit_account_id=debit_account.id,
        credit_account_id=credit_account.id,
        amount=money(receipt.amount),
        created_by_id=user.id,
        status="posted",
    )
    db.add(entry)
    return entry


def create_paid_case_fee_invoice(db: Session, *, case_fee: CaseFee, amount: Decimal, issue_date: date, notes: str | None = None) -> Invoice | None:
    if amount <= 0:
        return None
    matter_label = case_fee.matter.case_number if case_fee.matter else f"#{case_fee.matter_id}"
    invoice = Invoice(
        invoice_number=next_number(db, Invoice, "invoice_number", "INV"),
        client_id=case_fee.client_id,
        matter_id=case_fee.matter_id,
        issue_date=issue_date,
        due_date=issue_date,
        subtotal=amount,
        discount=Decimal("0"),
        tax=Decimal("0"),
        total_amount=amount,
        paid_amount=amount,
        status="paid",
        notes=notes or f"فاتورة تلقائية لمبلغ مدفوع من أتعاب القضية {matter_label}.",
    )
    db.add(invoice)
    db.flush()
    return invoice


def case_fee_income_date(case_fee: CaseFee, fallback: date | None = None) -> date:
    return case_fee.due_date or fallback or date.today()


def create_auto_case_fee_receipt(
    db: Session,
    *,
    case_fee: CaseFee,
    invoice: Invoice,
    amount: Decimal,
    received_at: date,
    user: User,
    notes: str | None = None,
) -> ReceiptVoucher | None:
    if amount <= 0:
        return None
    receipt = ReceiptVoucher(
        receipt_number=next_number(db, ReceiptVoucher, "receipt_number", "RV"),
        client_id=case_fee.client_id,
        matter_id=case_fee.matter_id,
        invoice_id=invoice.id,
        case_fee_id=case_fee.id,
        receipt_type="case_fee",
        amount=amount,
        payment_method="cash",
        received_at=received_at,
        received_by_id=user.id,
        reference_no=f"AUTO-CF-{case_fee.id}",
        notes=notes or "سند قبض تلقائي لمبلغ مدفوع عند إدخال أتعاب القضية.",
        status="active",
    )
    db.add(receipt)
    db.flush()
    return receipt


def is_cash_method(method: str | None) -> bool:
    return (method or "").strip() == "cash"


def recalculate_financial_account_balances(db: Session) -> None:
    cash_account = db.scalar(select(FinancialAccount).where(FinancialAccount.account_type == "cash").order_by(FinancialAccount.id))
    bank_account = db.scalar(select(FinancialAccount).where(FinancialAccount.account_type == "bank").order_by(FinancialAccount.id))
    if not cash_account and not bank_account:
        return
    balances = {
        "cash": money(cash_account.opening_balance) if cash_account else Decimal("0"),
        "bank": money(bank_account.opening_balance) if bank_account else Decimal("0"),
    }

    def bucket(method: str | None) -> str:
        return "cash" if is_cash_method(method) else "bank"

    for payment in db.scalars(select(Payment)).all():
        balances[bucket(payment.method)] += money(payment.amount)
    for receipt in db.scalars(select(ReceiptVoucher).where(ReceiptVoucher.status == "active")).all():
        balances[bucket(receipt.payment_method)] += money(receipt.amount)
    for expense in db.scalars(select(Expense).where(Expense.status == "active")).all():
        balances[bucket(expense.payment_method)] -= money(expense.amount)
    for voucher in db.scalars(select(PaymentVoucher).where(PaymentVoucher.status == "active")).all():
        balances[bucket(voucher.payment_method)] -= money(voucher.amount)

    if cash_account:
        cash_account.current_balance = balances["cash"]
    if bank_account:
        bank_account.current_balance = balances["bank"]


def overdue_filter_context(
    request: Request,
    q: str | None,
    delay_bucket: str | None,
    lawyer_id: str | None,
    matter_id: str | None,
    min_balance: str | None,
    max_balance: str | None,
) -> dict:
    overdue_values = request.query_params.getlist("overdue_only")
    overdue_only = "1" in overdue_values if overdue_values else True
    return {
        "q": (q or "").strip(),
        "delay_bucket": delay_bucket or "",
        "lawyer_id": int_or_none(lawyer_id),
        "matter_id": int_or_none(matter_id),
        "min_balance": decimal_filter(min_balance),
        "max_balance": decimal_filter(max_balance),
        "overdue_only": overdue_only,
    }


def overdue_reminder_message(client_name: str, balance: Decimal, due_date: date) -> str:
    return (
        f"السلام عليكم {client_name}،\n"
        "نود تذكيركم بوجود مبلغ مستحق لمكتب سعيد الشبيبي للمحاماة "
        f"بقيمة {balance:.2f} ريال عماني، وكان تاريخ الاستحقاق {due_date}.\n"
        "يرجى التواصل معنا لترتيب السداد أو الاستفسار.\n"
        "شاكرين لكم تعاونكم."
    )


def clamp_due_day(value: str | int) -> int:
    day = int(value)
    if day < 1 or day > 31:
        raise HTTPException(status_code=400, detail="يوم الاستحقاق يجب أن يكون بين 1 و31.")
    return day


def date_quality_or_400(date_status: str | None, date_note: str | None, value: str | None) -> tuple[str, str | None, date]:
    try:
        return validate_date_quality(date_status, date_note, parse_date(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def status_filter_value(value: str | None) -> str:
    value = normalize_date_status(value) if value else "all"
    return value if value in DATE_STATUS_FILTERS else "all"


def account_transaction_rows(db: Session, date_status: str = "all") -> list[dict]:
    rows: list[dict] = []

    def allowed(status: str | None) -> bool:
        return date_status == "all" or normalize_date_status(status) == date_status

    for payment in db.scalars(select(Payment).options(selectinload(Payment.invoice).selectinload(Invoice.client))).all():
        if not allowed(payment.date_status):
            continue
        rows.append(
            {
                "date": payment.payment_date,
                "kind": "إيراد",
                "source": "دفعة فاتورة",
                "party": payment.invoice.client.full_name if payment.invoice and payment.invoice.client else "-",
                "amount": money(payment.amount),
                "method": payment.method,
                "date_status": payment.date_status,
                "date_note": payment.date_note,
            }
        )
    for receipt in db.scalars(select(ReceiptVoucher).options(selectinload(ReceiptVoucher.client)).where(ReceiptVoucher.status == "active")).all():
        if not allowed(receipt.date_status):
            continue
        rows.append(
            {
                "date": receipt.received_at,
                "kind": "إيراد",
                "source": "سند قبض",
                "party": receipt.client.full_name if receipt.client else "-",
                "amount": money(receipt.amount),
                "method": receipt.payment_method,
                "date_status": receipt.date_status,
                "date_note": receipt.date_note,
            }
        )
    for expense in db.scalars(select(Expense).options(selectinload(Expense.matter)).where(Expense.status == "active")).all():
        if not allowed(expense.date_status):
            continue
        rows.append(
            {
                "date": expense.expense_date,
                "kind": "مصروف",
                "source": expense.category,
                "party": expense.matter.case_number if expense.matter else "عام",
                "amount": -money(expense.amount),
                "method": expense.payment_method,
                "date_status": expense.date_status,
                "date_note": expense.date_note,
            }
        )
    for voucher in db.scalars(select(PaymentVoucher).options(selectinload(PaymentVoucher.client)).where(PaymentVoucher.status == "active")).all():
        if not allowed(voucher.date_status):
            continue
        rows.append(
            {
                "date": voucher.paid_at,
                "kind": "مصروف",
                "source": voucher.expense_type,
                "party": voucher.client.full_name if voucher.client else voucher.beneficiary,
                "amount": -money(voucher.amount),
                "method": voucher.payment_method,
                "date_status": voucher.date_status,
                "date_note": voucher.date_note,
            }
        )
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows


def excel_response(filename: str, title: str, tables: list[dict]) -> Response:
    parts = [
        "\ufeff",
        "<html><head><meta charset='utf-8'>",
        "<style>body{direction:rtl;font-family:Tahoma,Arial} table{border-collapse:collapse;margin-bottom:24px} th,td{border:1px solid #999;padding:6px 10px;text-align:right;white-space:nowrap} th{background:#eef2f7;font-weight:bold} h2,h3{margin:12px 0}</style>",
        "</head><body>",
        f"<h2>{escape(title)}</h2>",
    ]
    for table in tables:
        parts.append(f"<h3>{escape(table['title'])}</h3>")
        parts.append("<table><thead><tr>")
        for heading in table["headers"]:
            parts.append(f"<th>{escape(str(heading))}</th>")
        parts.append("</tr></thead><tbody>")
        for row in table["rows"]:
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{escape(str(cell if cell is not None else '-'))}</td>")
            parts.append("</tr>")
        if not table["rows"]:
            parts.append(f"<tr><td colspan='{len(table['headers'])}'>لا توجد بيانات</td></tr>")
        parts.append("</tbody></table>")
    parts.append("</body></html>")
    return Response(
        "".join(parts),
        media_type="application/vnd.ms-excel; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.xls"'},
    )


def report_export_tables(db: Session, start: date | None, end: date | None) -> list[dict]:
    summary = accounting_summary(db, start, end)
    fixed_summary = fixed_monthly_expense_summary(db)
    date_quality = date_quality_counts(db, start, end)
    return [
        {
            "title": "ملخص التقرير المالي",
            "headers": ["البند", "القيمة"],
            "rows": [
                ["إجمالي الفواتير", summary["billed"]],
                ["الإيرادات", summary["revenue"]],
                ["المصروفات", summary["expenses"]],
                ["صافي الربح", summary["net_profit"]],
                ["المستحقات", summary["outstanding"]],
                ["فواتير متأخرة", summary["overdue_invoices"]],
            ],
        },
        {
            "title": "جودة تواريخ البيانات",
            "headers": ["الحالة", "عدد السجلات", "الإيرادات", "المصروفات", "الصافي"],
            "rows": [
                [row["label"], row["count"], row["revenue"], row["expenses"], row["net"]]
                for row in date_quality["statuses"].values()
            ],
        },
        {
            "title": "مؤشرات المصاريف الشهرية الثابتة",
            "headers": ["البند", "القيمة"],
            "rows": [
                ["إجمالي الإيرادات الشهرية", fixed_summary["monthly_revenue"]],
                ["إجمالي المصاريف الشهرية الثابتة", fixed_summary["monthly_total"]],
                ["صافي الربح التقريبي", fixed_summary["estimated_net_profit"]],
                ["نقطة التعادل الشهرية", fixed_summary["break_even_monthly"]],
                ["الاحتياج اليومي للتغطية", fixed_summary["daily_needed"]],
            ],
        },
    ]


@router.get("")
def accounting_dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    month_start = date.today().replace(day=1)
    overdue_report = overdue_clients_report(db)
    missing_case_fees_count = db.scalar(select(func.count()).select_from(missing_case_fees_stmt().subquery())) or 0
    return templates.TemplateResponse(
        "accounting/dashboard.html",
        {
            "request": request,
            "user": user,
            "summary": accounting_summary(db, month_start, date.today()),
            "fixed_expense_summary": fixed_monthly_expense_summary(db),
            "alerts": financial_alerts(db),
            "recent_receipts": db.scalars(select(ReceiptVoucher).options(selectinload(ReceiptVoucher.client)).order_by(ReceiptVoucher.created_at.desc()).limit(6)).all(),
            "recent_expenses": db.scalars(select(Expense).order_by(Expense.expense_date.desc()).limit(6)).all(),
            "overdue_installments": db.scalars(select(Installment).options(selectinload(Installment.client), selectinload(Installment.matter)).where(Installment.due_date < date.today(), Installment.status.in_(["pending", "overdue"])).limit(8)).all(),
            "overdue_report": overdue_report,
            "missing_case_fees_count": missing_case_fees_count,
        },
    )


@router.get("/clients")
def accounting_clients(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    rows = []
    for client in db.scalars(select(Client).order_by(Client.full_name)).all():
        agreed = db.scalar(select(func.coalesce(func.sum(CaseFee.fee_amount), 0)).where(CaseFee.client_id == client.id, CaseFee.is_cancelled.is_(False), CaseFee.status != "contingent", CaseFee.is_group_primary.is_(True))) or 0
        contingent = db.scalar(select(func.count(CaseFee.id)).where(CaseFee.client_id == client.id, CaseFee.is_cancelled.is_(False), CaseFee.status == "contingent", CaseFee.is_group_primary.is_(True))) or 0
        paid = db.scalar(select(func.coalesce(func.sum(CaseFee.paid_amount), 0)).where(CaseFee.client_id == client.id, CaseFee.is_cancelled.is_(False), CaseFee.is_group_primary.is_(True))) or 0
        invoice_total = db.scalar(select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(Invoice.client_id == client.id, Invoice.status != "cancelled")) or 0
        invoice_paid = db.scalar(select(func.coalesce(func.sum(Invoice.paid_amount), 0)).where(Invoice.client_id == client.id, Invoice.status != "cancelled")) or 0
        total_due = calculate_balance(agreed, paid) if agreed else calculate_balance(invoice_total, invoice_paid)
        rows.append(
            {
                "client_id": client.id,
                "client_name": client.full_name,
                "agreed": agreed,
                "contingent": contingent,
                "paid": paid or invoice_paid,
                "invoice_total": invoice_total,
                "invoice_paid": invoice_paid,
                "remaining": total_due,
            }
        )
    return templates.TemplateResponse("accounting/clients.html", {"request": request, "user": user, "rows": rows})


@router.get("/missing-case-fees")
def missing_case_fees_index(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_finance(user)
    stmt = missing_case_fees_stmt(q, status).order_by(Matter.opened_at.is_(None), Matter.opened_at.desc(), Matter.created_at.desc())
    matters = db.scalars(stmt).all()
    total_missing = db.scalar(select(func.count()).select_from(missing_case_fees_stmt().subquery())) or 0
    return templates.TemplateResponse(
        "accounting/missing_case_fees.html",
        {
            "request": request,
            "user": user,
            "matters": matters,
            "filters": {"q": q or "", "status": status or ""},
            "total_missing": total_missing,
            "filtered_count": len(matters),
        },
    )


@router.get("/missing-case-fees/export.xls")
def missing_case_fees_export(q: str | None = None, status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    stmt = (
        missing_case_fees_stmt(q, status)
        .options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
        .order_by(Matter.opened_at.is_(None), Matter.opened_at.desc(), Matter.created_at.desc())
    )
    matters = db.scalars(stmt).all()
    rows = [
        [
            matter.case_number,
            matter.ministry_case_number or "-",
            matter.title,
            matter.client.full_name if matter.client else "-",
            matter.court_name or "-",
            CASE_STATUSES.get(matter.status, matter.status),
            matter.opened_at or "-",
            matter.assigned_lawyer.full_name if matter.assigned_lawyer else "-",
        ]
        for matter in matters
    ]
    return excel_response(
        "missing-case-fees",
        "قضايا بلا أتعاب",
        [
            {
                "title": "القضايا التي لا يوجد لها سجل أتعاب نشط",
                "headers": ["رقم المكتب", "رقم الدعوى", "القضية", "العميل", "المحكمة", "الحالة", "تاريخ الفتح", "المحامي"],
                "rows": rows,
            }
        ],
    )


@router.get("/case-fees")
def case_fees_index(request: Request, matter_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    fees = db.scalars(select(CaseFee).options(selectinload(CaseFee.client), selectinload(CaseFee.matter)).order_by(CaseFee.created_at.desc())).all()
    display_fees = [fee for fee in fees if fee.is_group_primary]
    group_labels = case_fee_group_labels(fees)
    success_fees = [fee for fee in display_fees if fee.payment_plan in {"success_fee", "advance_success_fee"}]
    judgment_fees = [fee for fee in display_fees if fee.payment_plan == "advance_judgment"]
    standard_fees = [fee for fee in display_fees if fee.payment_plan not in {"success_fee", "advance_success_fee", "advance_judgment"}]
    standard_summary = {
        "count": len(standard_fees),
        "total": sum((money(fee.fee_amount) for fee in standard_fees if not fee.is_cancelled), Decimal("0")),
        "paid": sum((money(fee.paid_amount) for fee in standard_fees if not fee.is_cancelled), Decimal("0")),
    }
    success_summary = {
        "count": len([fee for fee in success_fees if not fee.is_cancelled]),
        "pending": len([fee for fee in success_fees if fee.status == "contingent" and not fee.is_cancelled]),
        "converted_total": sum((money(fee.fee_amount) for fee in success_fees if fee.status != "contingent" and not fee.is_cancelled), Decimal("0")),
    }
    judgment_summary = {
        "count": len([fee for fee in judgment_fees if not fee.is_cancelled]),
        "pending": len([fee for fee in judgment_fees if fee.status == "contingent" and not fee.is_cancelled]),
        "advance_paid": sum((money(fee.paid_amount) for fee in judgment_fees if not fee.is_cancelled), Decimal("0")),
        "remaining_pending": sum((calculate_balance(fee.fee_amount, fee.paid_amount) for fee in judgment_fees if fee.status == "contingent" and not fee.is_cancelled), Decimal("0")),
        "converted_total": sum((money(fee.fee_amount) for fee in judgment_fees if fee.status != "contingent" and not fee.is_cancelled), Decimal("0")),
    }
    return templates.TemplateResponse(
        "accounting/case_fees.html",
        {
            "request": request,
            "user": user,
            "fees": fees,
            "standard_fees": standard_fees,
            "success_fees": success_fees,
            "judgment_fees": judgment_fees,
            "group_labels": group_labels,
            "standard_summary": standard_summary,
            "success_summary": success_summary,
            "judgment_summary": judgment_summary,
            "payment_plans": CASE_FEE_PAYMENT_PLANS,
            "fee_statuses": CASE_FEE_STATUSES,
            "selected_matter_id": int_or_none(matter_id) or "",
            **get_form_context(db),
        },
    )


@router.post("/case-fees")
def case_fee_create(request: Request, matter_ids: list[int] | None = Form(None), fee_amount: str = Form("0"), success_percentage: str = Form("0"), payment_plan: str = Form("one_time"), advance_payment: str = Form("0"), monthly_installment: str = Form("0"), due_date: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    if payment_plan not in CASE_FEE_PAYMENT_PLANS:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير صحيحة.")
    selected_ids = list(dict.fromkeys(matter_ids or []))
    if not selected_ids:
        raise HTTPException(status_code=400, detail="اختر قضية واحدة على الأقل.")
    matters_by_id = {matter.id: matter for matter in db.scalars(select(Matter).where(Matter.id.in_(selected_ids))).all()}
    matters = [matters_by_id[matter_id] for matter_id in selected_ids if matter_id in matters_by_id]
    if len(matters) != len(selected_ids):
        raise HTTPException(status_code=404, detail="القضية غير موجودة.")
    if len({matter.client_id for matter in matters}) != 1:
        raise HTTPException(status_code=400, detail="يجب أن تكون كل القضايا المختارة لنفس العميل.")
    paid_existing_fee = db.scalar(
        select(CaseFee)
        .where(CaseFee.matter_id.in_(selected_ids), CaseFee.is_cancelled.is_(False))
        .where((CaseFee.status == "paid") | ((CaseFee.fee_amount > 0) & (CaseFee.paid_amount >= CaseFee.fee_amount)))
        .limit(1)
    )
    if paid_existing_fee:
        raise HTTPException(status_code=400, detail="توجد أتعاب مدفوعة لهذه القضية، ولا يمكن تسجيل أتعاب أو دفعة جديدة عليها.")
    paid = parse_decimal(advance_payment)
    fee = Decimal("0") if payment_plan in {"success_fee", "advance_success_fee"} else parse_decimal(fee_amount)
    percentage = parse_decimal(success_percentage) if payment_plan in {"success_fee", "advance_success_fee"} else None
    if payment_plan in {"success_fee", "advance_success_fee", "advance_judgment"}:
        status = "paid" if payment_plan == "advance_judgment" and fee > 0 and paid >= fee else "contingent"
    else:
        status = "paid" if paid >= fee else ("partial" if paid > 0 else "unpaid")
    due = None if payment_plan in {"success_fee", "advance_success_fee", "advance_judgment"} else parse_date(due_date)
    group_key = f"CFG-{uuid4().hex[:12]}" if len(matters) > 1 else None
    group_total = fee if group_key else None
    monthly = parse_decimal(monthly_installment)
    items = []
    for index, matter in enumerate(matters):
        is_primary = index == 0
        item = CaseFee(
            matter_id=matter.id,
            client_id=matter.client_id,
            fee_amount=fee if is_primary else Decimal("0"),
            success_percentage=percentage if is_primary else None,
            payment_plan=payment_plan,
            group_key=group_key,
            group_total_amount=group_total,
            is_group_primary=is_primary,
            advance_payment=paid if is_primary else Decimal("0"),
            monthly_installment=monthly if is_primary else Decimal("0"),
            due_date=due if is_primary else None,
            paid_amount=paid if is_primary else Decimal("0"),
            status=status,
            notes=none_if_empty(notes),
            is_cancelled=False,
        )
        db.add(item)
        items.append(item)
    db.flush()
    journal_entry = None
    auto_invoice = None
    auto_receipt = None
    if items[0].is_group_primary and paid > 0:
        income_date = case_fee_income_date(items[0])
        auto_invoice = create_paid_case_fee_invoice(
            db,
            case_fee=items[0],
            amount=paid,
            issue_date=income_date,
            notes="فاتورة تلقائية لمبلغ مدفوع مباشرة عند إضافة أتعاب القضية.",
        )
        if auto_invoice:
            auto_receipt = create_auto_case_fee_receipt(
                db,
                case_fee=items[0],
                invoice=auto_invoice,
                amount=paid,
                received_at=income_date,
                user=user,
            )
        journal_entry = create_paid_case_fee_journal(db, case_fee=items[0], amount=paid, user=user, entry_date=income_date)
        db.flush()
    log_action(db, user=user, action="create_case_fee", entity_type="case_fee", entity_id=items[0].id, new_value={"matter_ids": selected_ids, "fee_amount": str(fee), "group_key": group_key}, request=request)
    if auto_invoice:
        log_action(db, user=user, action="create_invoice", entity_type="invoice", entity_id=auto_invoice.id, new_value={"source": "case_fee_paid_on_create", "case_fee_id": items[0].id, "amount": str(paid)}, request=request)
    if auto_receipt:
        log_action(db, user=user, action="create_receipt_voucher", entity_type="receipt_voucher", entity_id=auto_receipt.id, new_value={"source": "case_fee_paid_on_create", "case_fee_id": items[0].id, "amount": str(paid)}, request=request)
    if journal_entry:
        log_action(db, user=user, action="create_journal_entry", entity_type="journal_entry", entity_id=journal_entry.id, new_value={"source": "case_fee_paid_on_create", "case_fee_id": items[0].id, "amount": str(paid)}, request=request)
    db.commit()
    return RedirectResponse("/accounting/case-fees", status_code=303)


@router.post("/case-fees/{fee_id}/mark-won")
def case_fee_mark_won(request: Request, fee_id: int, won_amount: str = Form(...), due_date: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    item = db.get(CaseFee, fee_id)
    if not item:
        raise HTTPException(status_code=404, detail="سجل الأتعاب غير موجود.")
    if item.payment_plan not in {"success_fee", "advance_success_fee"} or item.is_cancelled:
        raise HTTPException(status_code=400, detail="لا يمكن تحويل هذا السجل كدفع عند الفوز.")
    won = parse_decimal(won_amount)
    percentage = item.success_percentage or Decimal("0")
    advance = money(item.advance_payment) if item.payment_plan == "advance_success_fee" else Decimal("0")
    item.won_amount = won
    item.fee_amount = (advance + (won * percentage / Decimal("100"))).quantize(Decimal("0.01"))
    item.status = "paid" if money(item.paid_amount) >= money(item.fee_amount) else ("partial" if money(item.paid_amount) > 0 else "unpaid")
    item.due_date = parse_date(due_date) or date.today()
    for member in case_fee_group_members(db, item):
        if member.id == item.id:
            continue
        member.status = item.status
        member.due_date = item.due_date
    log_action(db, user=user, action="mark_success_fee_due", entity_type="case_fee", entity_id=item.id, new_value={"status": item.status, "due_date": item.due_date, "won_amount": str(won), "fee_amount": str(item.fee_amount)}, request=request)
    db.commit()
    return RedirectResponse("/accounting/case-fees", status_code=303)


@router.post("/case-fees/{fee_id}/mark-judgment-issued")
def case_fee_mark_judgment_issued(request: Request, fee_id: int, due_date: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    item = db.get(CaseFee, fee_id)
    if not item:
        raise HTTPException(status_code=404, detail="سجل الأتعاب غير موجود.")
    if item.payment_plan != "advance_judgment" or item.is_cancelled:
        raise HTTPException(status_code=400, detail="لا يمكن تحويل هذا السجل كأتعاب عند الحكم.")
    item.status = "paid" if money(item.paid_amount) >= money(item.fee_amount) else ("partial" if money(item.paid_amount) > 0 else "unpaid")
    item.due_date = parse_date(due_date) or date.today()
    for member in case_fee_group_members(db, item):
        if member.id == item.id:
            continue
        member.status = item.status
        member.due_date = item.due_date
    log_action(db, user=user, action="mark_judgment_fee_due", entity_type="case_fee", entity_id=item.id, new_value={"status": item.status, "due_date": item.due_date, "fee_amount": str(item.fee_amount), "paid_amount": str(item.paid_amount)}, request=request)
    db.commit()
    return RedirectResponse("/accounting/case-fees", status_code=303)


@router.post("/case-fees/{fee_id}/cancel")
def case_fee_cancel(request: Request, fee_id: int, cancel_reason: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    item = db.get(CaseFee, fee_id)
    if not item:
        raise HTTPException(status_code=404, detail="سجل الأتعاب غير موجود.")
    for member in case_fee_group_members(db, item):
        member.is_cancelled = True
        member.status = "cancelled"
        member.cancel_reason = cancel_reason
    log_action(db, user=user, action="cancel_case_fee", entity_type="case_fee", entity_id=item.id, new_value={"reason": cancel_reason}, request=request)
    db.commit()
    return RedirectResponse("/accounting/case-fees", status_code=303)


@router.get("/receipts")
def receipts_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    receipts = db.scalars(select(ReceiptVoucher).options(selectinload(ReceiptVoucher.client), selectinload(ReceiptVoucher.matter), selectinload(ReceiptVoucher.invoice), selectinload(ReceiptVoucher.case_fee)).order_by(ReceiptVoucher.received_at.desc())).all()
    return templates.TemplateResponse(
        "accounting/receipts.html",
        {
            "request": request,
            "user": user,
            "receipts": receipts,
            "next_no": next_number(db, ReceiptVoucher, "receipt_number", "RV"),
            **get_form_context(db),
            "methods": PAYMENT_METHODS_ACCOUNTING,
            "receipt_types": RECEIPT_TYPES,
            "case_fee_payment_context": case_fee_payment_context(db),
            "receipt_case_fee_labels": receipt_case_fee_labels(db, receipts),
            "date_status_options": DATE_STATUS_OPTIONS,
            "date_status_badge": date_status_badge,
        },
    )


@router.post("/receipts")
async def receipt_create(request: Request, client_id: int = Form(...), matter_id: str = Form(""), invoice_id: str = Form(""), receipt_type: str = Form("case_fee"), amount: str = Form(...), payment_method: str = Form("cash"), received_at: str = Form(""), date_status: str = Form("confirmed"), date_note: str = Form(""), reference_no: str = Form(""), notes: str = Form(""), attachment: UploadFile | None = File(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    if receipt_type not in RECEIPT_TYPES:
        raise HTTPException(status_code=400, detail="نوع سند القبض غير صحيح.")
    date_status_value, date_note_value, received_date = date_quality_or_400(date_status, date_note, received_at)
    parsed_matter_id = validate_client_matter(db, client_id, matter_id) if date_status_value != "unknown" else None
    parsed_invoice_id = validate_client_invoice(db, client_id, invoice_id) if date_status_value != "unknown" else None
    amount_d = parse_decimal(amount)
    if amount_d <= 0:
        raise HTTPException(status_code=400, detail="مبلغ سند القبض يجب أن يكون أكبر من صفر.")
    invoice = db.get(Invoice, parsed_invoice_id) if parsed_invoice_id else None
    case_fee = None
    if date_status_value == "unknown":
        receipt_type = "general"
        parsed_matter_id = None
        parsed_invoice_id = None
        notes = f"{OPENING_BALANCE_LABEL} - {OLD_UNDATED_PAYMENT_LABEL}. {notes}".strip()
    elif invoice:
        receipt_type = "invoice"
        if parsed_matter_id and invoice.matter_id and parsed_matter_id != invoice.matter_id:
            raise HTTPException(status_code=400, detail="القضية المختارة لا تطابق قضية الفاتورة.")
        parsed_matter_id = invoice.matter_id or parsed_matter_id
        apply_invoice_receipt(db, invoice, amount_d)
    elif receipt_type == "case_fee":
        if not parsed_matter_id:
            raise HTTPException(status_code=400, detail="اختر القضية عند تسجيل سند قبض أتعاب قضية.")
        case_fee = apply_case_fee_receipt(db, parsed_matter_id, amount_d)
        if not case_fee:
            raise HTTPException(status_code=400, detail="لا توجد أتعاب قابلة للسداد لهذه القضية.")
        invoice = create_paid_case_fee_invoice(
            db,
            case_fee=case_fee,
            amount=amount_d,
            issue_date=received_date,
            notes="فاتورة تلقائية لسند قبض أتعاب قضية.",
        )
        if invoice:
            parsed_invoice_id = invoice.id
    else:
        parsed_matter_id = None
    attachment_url = None
    if attachment and attachment.filename:
        attachment_url, _, _, _ = await save_upload(attachment)
    item = ReceiptVoucher(receipt_number=next_number(db, ReceiptVoucher, "receipt_number", "RV"), client_id=client_id, matter_id=parsed_matter_id, invoice_id=parsed_invoice_id, case_fee_id=case_fee.id if case_fee else None, receipt_type=receipt_type, amount=amount_d, payment_method=payment_method, received_at=received_date, date_status=date_status_value, date_note=date_note_value, received_by_id=user.id, reference_no=none_if_empty(reference_no), attachment_url=attachment_url, notes=none_if_empty(notes), status="active")
    db.add(item)
    db.flush()
    if invoice and receipt_type == "case_fee":
        log_action(db, user=user, action="create_invoice", entity_type="invoice", entity_id=invoice.id, new_value={"source": "case_fee_receipt", "case_fee_id": case_fee.id if case_fee else None, "amount": str(amount_d)}, request=request)
    journal_entry = create_paid_case_fee_journal(db, case_fee=case_fee, amount=amount_d, user=user, entry_date=received_date, date_status=date_status_value, date_note=date_note_value) if case_fee and receipt_type == "case_fee" else None
    if journal_entry:
        db.flush()
        log_action(db, user=user, action="create_journal_entry", entity_type="journal_entry", entity_id=journal_entry.id, new_value={"source": "case_fee_receipt", "case_fee_id": case_fee.id, "amount": str(amount_d)}, request=request)
    log_action(db, user=user, action="create_receipt_voucher", entity_type="receipt_voucher", entity_id=item.id, new_value={"amount": amount}, request=request)
    db.commit()
    return RedirectResponse("/accounting/receipts", status_code=303)


@router.get("/receipts/{receipt_id}/print")
def receipt_print(request: Request, receipt_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    receipt = db.scalar(select(ReceiptVoucher).where(ReceiptVoucher.id == receipt_id).options(selectinload(ReceiptVoucher.client), selectinload(ReceiptVoucher.matter), selectinload(ReceiptVoucher.invoice), selectinload(ReceiptVoucher.case_fee), selectinload(ReceiptVoucher.received_by)))
    return templates.TemplateResponse("accounting/receipt_print.html", {"request": request, "user": user, "receipt": receipt, "methods": PAYMENT_METHODS_ACCOUNTING, "receipt_types": RECEIPT_TYPES, "receipt_case_fee_labels": receipt_case_fee_labels(db, [receipt] if receipt else [])})


@router.post("/receipts/{receipt_id}/cancel")
def receipt_cancel(request: Request, receipt_id: int, cancel_reason: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    receipt = db.scalar(
        select(ReceiptVoucher)
        .where(ReceiptVoucher.id == receipt_id)
        .options(selectinload(ReceiptVoucher.invoice), selectinload(ReceiptVoucher.case_fee))
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="سند القبض غير موجود.")
    if receipt.status != "active":
        raise HTTPException(status_code=400, detail="سند القبض ملغي مسبقاً.")
    if (receipt.receipt_type or "case_fee") == "case_fee":
        reverse_case_fee_receipt(db, receipt)
        if receipt.invoice_id:
            reverse_invoice_receipt(db, receipt)
        reversal_entry = create_case_fee_receipt_reversal_journal(db, receipt=receipt, user=user)
        if reversal_entry:
            db.flush()
            log_action(db, user=user, action="create_journal_entry", entity_type="journal_entry", entity_id=reversal_entry.id, new_value={"source": "cancel_case_fee_receipt", "receipt_id": receipt.id, "amount": str(receipt.amount)}, request=request)
    elif receipt.invoice_id:
        reverse_invoice_receipt(db, receipt)
    receipt.status = "cancelled"
    receipt.cancel_reason = cancel_reason
    log_action(db, user=user, action="cancel_receipt_voucher", entity_type="receipt_voucher", entity_id=receipt.id, new_value={"reason": cancel_reason}, request=request)
    db.commit()
    return RedirectResponse("/accounting/receipts", status_code=303)


@router.get("/payment-vouchers")
def payment_vouchers_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    vouchers = db.scalars(select(PaymentVoucher).options(selectinload(PaymentVoucher.client), selectinload(PaymentVoucher.matter)).order_by(PaymentVoucher.paid_at.desc())).all()
    return templates.TemplateResponse("accounting/payment_vouchers.html", {"request": request, "user": user, "vouchers": vouchers, "next_no": next_number(db, PaymentVoucher, "voucher_number", "PV"), "categories": EXPENSE_CATEGORIES, "methods": PAYMENT_METHODS_ACCOUNTING, "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge, **get_form_context(db)})


@router.post("/payment-vouchers")
async def payment_voucher_create(request: Request, expense_type: str = Form(...), beneficiary: str = Form(...), client_id: str = Form(""), matter_id: str = Form(""), amount: str = Form(...), payment_method: str = Form("cash"), paid_at: str = Form(""), date_status: str = Form("confirmed"), date_note: str = Form(""), notes: str = Form(""), attachment: UploadFile | None = File(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    date_status_value, date_note_value, paid_date = date_quality_or_400(date_status, date_note, paid_at)
    parsed_client_id = int_or_none(client_id)
    parsed_matter_id = validate_client_matter(db, parsed_client_id, matter_id) if date_status_value != "unknown" else None
    if date_status_value == "unknown":
        expense_type = OLD_UNDATED_PAYMENT_LABEL
        beneficiary = beneficiary or OPENING_BALANCE_LABEL
        notes = f"{OPENING_BALANCE_LABEL} - {OLD_UNDATED_PAYMENT_LABEL}. {notes}".strip()
    amount_d = parse_decimal(amount)
    approval_status = "pending" if amount_d > APPROVAL_LIMIT and user.role != "admin" else "approved"
    attachment_url = None
    if attachment and attachment.filename:
        attachment_url, _, _, _ = await save_upload(attachment)
    item = PaymentVoucher(voucher_number=next_number(db, PaymentVoucher, "voucher_number", "PV"), client_id=parsed_client_id, matter_id=parsed_matter_id, expense_type=expense_type, beneficiary=beneficiary, amount=amount_d, payment_method=payment_method, paid_at=paid_date, date_status=date_status_value, date_note=date_note_value, attachment_url=attachment_url, notes=none_if_empty(notes), created_by_id=user.id, approval_status=approval_status, approved_by_id=user.id if approval_status == "approved" else None, status="active")
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_payment_voucher", entity_type="payment_voucher", entity_id=item.id, new_value={"amount": amount}, request=request)
    db.commit()
    return RedirectResponse("/accounting/payment-vouchers", status_code=303)


@router.post("/payment-vouchers/{voucher_id}/approve")
def payment_voucher_approve(request: Request, voucher_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"admin"})
    item = db.get(PaymentVoucher, voucher_id)
    item.approval_status = "approved"
    item.approved_by_id = user.id
    log_action(db, user=user, action="approve_payment_voucher", entity_type="payment_voucher", entity_id=item.id, request=request)
    db.commit()
    return RedirectResponse("/accounting/payment-vouchers", status_code=303)


@router.get("/expenses")
def expenses_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    expenses = db.scalars(select(Expense).options(selectinload(Expense.matter), selectinload(Expense.added_by)).where(Expense.status == "active").order_by(Expense.expense_date.desc())).all()
    return templates.TemplateResponse("accounting/expenses.html", {"request": request, "user": user, "expenses": expenses, "categories": EXPENSE_CATEGORIES, "methods": PAYMENT_METHODS_ACCOUNTING, "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge, **get_form_context(db)})


@router.post("/expenses")
async def expense_create(request: Request, category: str = Form(...), amount: str = Form(...), expense_date: str = Form(""), payment_method: str = Form("cash"), matter_id: str = Form(""), date_status: str = Form("confirmed"), date_note: str = Form(""), notes: str = Form(""), attachment: UploadFile | None = File(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    date_status_value, date_note_value, expense_date_value = date_quality_or_400(date_status, date_note, expense_date)
    if date_status_value == "unknown":
        category = OLD_UNDATED_PAYMENT_LABEL
        matter_id = ""
        notes = f"{OPENING_BALANCE_LABEL} - {OLD_UNDATED_PAYMENT_LABEL}. {notes}".strip()
    attachment_url = None
    if attachment and attachment.filename:
        attachment_url, _, _, _ = await save_upload(attachment)
    item = Expense(category=category, amount=parse_decimal(amount), expense_date=expense_date_value, date_status=date_status_value, date_note=date_note_value, payment_method=payment_method, matter_id=int_or_none(matter_id), added_by_id=user.id, attachment_url=attachment_url, notes=none_if_empty(notes), status="active")
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_expense", entity_type="expense", entity_id=item.id, new_value={"amount": amount, "category": category}, request=request)
    db.commit()
    return RedirectResponse("/accounting/expenses", status_code=303)


@router.post("/expenses/{expense_id}/delete")
def expense_delete(request: Request, expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    item = db.get(Expense, expense_id)
    if not item:
        raise HTTPException(status_code=404, detail="المصروف غير موجود.")
    if item.status != "active":
        return RedirectResponse("/accounting/expenses", status_code=303)
    old_value = {
        "category": item.category,
        "amount": str(item.amount),
        "expense_date": str(item.expense_date),
        "date_status": item.date_status,
    }
    item.status = "cancelled"
    item.cancel_reason = "حذف من شاشة المصروفات"
    log_action(db, user=user, action="delete_expense", entity_type="expense", entity_id=item.id, old_value=old_value, request=request)
    db.commit()
    return RedirectResponse("/accounting/expenses", status_code=303)


@router.get("/salaries")
def salaries_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.post("/salaries")
def salary_create(request: Request, employee_id: int = Form(...), salary_month: str = Form(...), base_salary: str = Form("0"), allowances: str = Form("0"), deductions: str = Form("0"), advances: str = Form("0"), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.get("/installments")
def installments_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    installments = db.scalars(select(Installment).options(selectinload(Installment.client), selectinload(Installment.matter)).order_by(Installment.due_date)).all()
    return templates.TemplateResponse("accounting/installments.html", {"request": request, "user": user, "installments": installments, **get_form_context(db)})


@router.post("/installments")
def installment_create(request: Request, client_id: int = Form(...), matter_id: str = Form(""), amount: str = Form(...), due_date: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    item = Installment(client_id=client_id, matter_id=int_or_none(matter_id), amount=parse_decimal(amount), due_date=parse_date(due_date) or date.today(), paid_amount=Decimal("0"), status="pending", notes=none_if_empty(notes))
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_installment", entity_type="installment", entity_id=item.id, new_value={"amount": amount}, request=request)
    db.commit()
    return RedirectResponse("/accounting/installments", status_code=303)


@router.get("/fixed-expenses")
def fixed_expenses_index(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_fixed_expense_view(user)
    stmt = select(FixedMonthlyExpense)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(FixedMonthlyExpense.title.ilike(like), FixedMonthlyExpense.vendor_name.ilike(like)))
    if category:
        stmt = stmt.where(FixedMonthlyExpense.category == category)
    if status == "active":
        stmt = stmt.where(FixedMonthlyExpense.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(FixedMonthlyExpense.is_active.is_(False))
    expenses = db.scalars(stmt.order_by(FixedMonthlyExpense.is_active.desc(), FixedMonthlyExpense.due_day, FixedMonthlyExpense.title)).all()
    return templates.TemplateResponse(
        "accounting/fixed_expenses.html",
        {
            "request": request,
            "user": user,
            "expenses": expenses,
            "summary": fixed_monthly_expense_summary(db),
            "filters": {"q": q or "", "category": category or "", "status": status or ""},
            "categories": FIXED_EXPENSE_CATEGORIES,
            "payment_methods": FIXED_EXPENSE_PAYMENT_METHODS,
            "can_write_fixed_expenses": user.role in {"admin", "accountant"},
            "can_delete_fixed_expenses": user.role == "admin",
        },
    )


@router.post("/fixed-expenses")
def fixed_expense_create(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    amount: str = Form(...),
    due_day: str = Form(...),
    payment_method: str = Form("cash"),
    vendor_name: str = Form(""),
    notes: str = Form(""),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_fixed_expense_write(user)
    item = FixedMonthlyExpense(
        title=title.strip(),
        category=category,
        amount=parse_decimal(amount),
        due_day=clamp_due_day(due_day),
        payment_method=payment_method,
        vendor_name=none_if_empty(vendor_name),
        notes=none_if_empty(notes),
        is_active=is_active == "1",
    )
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_fixed_monthly_expense", entity_type="fixed_monthly_expense", entity_id=item.id, new_value={"title": item.title, "amount": str(item.amount)}, request=request)
    db.commit()
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.post("/fixed-expenses/{expense_id}/update")
def fixed_expense_update(
    request: Request,
    expense_id: int,
    title: str = Form(...),
    category: str = Form(...),
    amount: str = Form(...),
    due_day: str = Form(...),
    payment_method: str = Form("cash"),
    vendor_name: str = Form(""),
    notes: str = Form(""),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_fixed_expense_write(user)
    item = db.get(FixedMonthlyExpense, expense_id)
    if not item:
        raise HTTPException(status_code=404, detail="المصروف الثابت غير موجود.")
    old_value = {"title": item.title, "category": item.category, "amount": str(item.amount), "due_day": item.due_day, "is_active": item.is_active}
    item.title = title.strip()
    item.category = category
    item.amount = parse_decimal(amount)
    item.due_day = clamp_due_day(due_day)
    item.payment_method = payment_method
    item.vendor_name = none_if_empty(vendor_name)
    item.notes = none_if_empty(notes)
    item.is_active = is_active == "1"
    log_action(db, user=user, action="update_fixed_monthly_expense", entity_type="fixed_monthly_expense", entity_id=item.id, old_value=old_value, new_value={"title": item.title, "category": item.category, "amount": str(item.amount), "due_day": item.due_day, "is_active": item.is_active}, request=request)
    db.commit()
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.post("/fixed-expenses/{expense_id}/toggle")
def fixed_expense_toggle(request: Request, expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_fixed_expense_write(user)
    item = db.get(FixedMonthlyExpense, expense_id)
    if not item:
        raise HTTPException(status_code=404, detail="المصروف الثابت غير موجود.")
    old_value = {"is_active": item.is_active}
    item.is_active = not item.is_active
    log_action(db, user=user, action="toggle_fixed_monthly_expense", entity_type="fixed_monthly_expense", entity_id=item.id, old_value=old_value, new_value={"is_active": item.is_active}, request=request)
    db.commit()
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.post("/fixed-expenses/{expense_id}/delete")
def fixed_expense_delete(request: Request, expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"admin"})
    item = db.get(FixedMonthlyExpense, expense_id)
    if not item:
        raise HTTPException(status_code=404, detail="المصروف الثابت غير موجود.")
    old_value = {"title": item.title, "category": item.category, "amount": str(item.amount), "due_day": item.due_day}
    log_action(db, user=user, action="delete_fixed_monthly_expense", entity_type="fixed_monthly_expense", entity_id=item.id, old_value=old_value, request=request)
    db.delete(item)
    db.commit()
    return RedirectResponse("/accounting/fixed-expenses", status_code=303)


@router.get("/accounts")
def accounts_index(request: Request, date_status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    selected_status = status_filter_value(date_status)
    recalculate_financial_account_balances(db)
    db.commit()
    accounts = db.scalars(select(FinancialAccount).order_by(FinancialAccount.account_name)).all()
    return templates.TemplateResponse("accounting/accounts.html", {"request": request, "user": user, "accounts": accounts, "transactions": account_transaction_rows(db, selected_status), "date_status_filters": DATE_STATUS_FILTERS, "selected_date_status": selected_status, "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge})


@router.get("/historical-date-review")
def historical_date_review(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    rows = historical_date_review_rows(db)
    return templates.TemplateResponse("accounting/historical_date_review.html", {"request": request, "user": user, "rows": rows, "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge})


@router.get("/chart")
def chart_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    accounts = db.scalars(select(ChartAccount).order_by(ChartAccount.code)).all()
    return templates.TemplateResponse("accounting/chart.html", {"request": request, "user": user, "accounts": accounts})


@router.get("/journal")
def journal_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    entries = db.scalars(select(JournalEntry).options(selectinload(JournalEntry.debit_account), selectinload(JournalEntry.credit_account)).order_by(JournalEntry.entry_date.desc())).all()
    accounts = db.scalars(select(ChartAccount).where(ChartAccount.is_active.is_(True)).order_by(ChartAccount.code)).all()
    return templates.TemplateResponse("accounting/journal.html", {"request": request, "user": user, "entries": entries, "accounts": accounts, "next_no": next_number(db, JournalEntry, "entry_number", "JE"), "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge})


@router.post("/journal")
def journal_create(request: Request, entry_date: str = Form(""), date_status: str = Form("confirmed"), date_note: str = Form(""), description: str = Form(...), debit_account_id: int = Form(...), credit_account_id: int = Form(...), amount: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    date_status_value, date_note_value, entry_date_value = date_quality_or_400(date_status, date_note, entry_date)
    item = JournalEntry(entry_number=next_number(db, JournalEntry, "entry_number", "JE"), entry_date=entry_date_value, date_status=date_status_value, date_note=date_note_value, description=description, debit_account_id=debit_account_id, credit_account_id=credit_account_id, amount=parse_decimal(amount), created_by_id=user.id, status="posted")
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_journal_entry", entity_type="journal_entry", entity_id=item.id, new_value={"amount": amount}, request=request)
    db.commit()
    return RedirectResponse("/accounting/journal", status_code=303)


@router.get("/reports")
def accounting_reports(request: Request, start_date: str | None = None, end_date: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    start = parse_date(start_date)
    end = parse_date(end_date)
    return templates.TemplateResponse("accounting/reports.html", {"request": request, "user": user, "summary": accounting_summary(db, start, end), "fixed_expense_summary": fixed_monthly_expense_summary(db), "date_quality": date_quality_counts(db, start, end), "start_date": start_date or "", "end_date": end_date or ""})


@router.get("/reports/export.xls")
def accounting_reports_export(start_date: str | None = None, end_date: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_finance(user)
    start = parse_date(start_date)
    end = parse_date(end_date)
    period = f"{start_date or 'all'}-{end_date or 'all'}"
    return excel_response(
        f"accounting-report-{period}",
        "التقرير المالي",
        report_export_tables(db, start, end),
    )


@router.get("/overdue-clients")
def overdue_clients_index(
    request: Request,
    q: str | None = None,
    delay_bucket: str | None = None,
    lawyer_id: str | None = None,
    matter_id: str | None = None,
    min_balance: str | None = None,
    max_balance: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_finance(user)
    filters = overdue_filter_context(request, q, delay_bucket, lawyer_id, matter_id, min_balance, max_balance)
    report = overdue_clients_report(db, filters)
    visible_filters = {
        "q": filters["q"],
        "delay_bucket": filters["delay_bucket"],
        "lawyer_id": filters["lawyer_id"] or "",
        "matter_id": filters["matter_id"] or "",
        "min_balance": min_balance or "",
        "max_balance": max_balance or "",
        "overdue_only": filters["overdue_only"],
    }
    return templates.TemplateResponse(
        "accounting/overdue_clients.html",
        {
            "request": request,
            "user": user,
            "rows": report["rows"],
            "overdue_summary": report["summary"],
            "filters": visible_filters,
            "delay_buckets": {
                "simple": "متأخر بسيط: 1 إلى 7 أيام",
                "medium": "متأخر متوسط: 8 إلى 30 يوم",
                "high": "متعثر عالي الخطورة: أكثر من 30 يوم",
            },
            **get_form_context(db),
        },
    )


@router.post("/overdue-clients/whatsapp-reminder")
def overdue_whatsapp_reminder(
    request: Request,
    source_type: str = Form(...),
    source_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_finance(user)
    if source_type == "invoice":
        item = db.scalar(
            select(Invoice)
            .where(Invoice.id == source_id)
            .options(selectinload(Invoice.client), selectinload(Invoice.matter))
        )
        if not item:
            raise HTTPException(status_code=404, detail="الفاتورة غير موجودة.")
        client = item.client
        matter = item.matter
        due_date = item.due_date
        balance = calculate_balance(item.total_amount, item.paid_amount)
        entity_type = "invoice"
    elif source_type == "installment":
        item = db.scalar(
            select(Installment)
            .where(Installment.id == source_id)
            .options(selectinload(Installment.client), selectinload(Installment.matter))
        )
        if not item:
            raise HTTPException(status_code=404, detail="القسط غير موجود.")
        client = item.client
        matter = item.matter
        due_date = item.due_date
        balance = calculate_balance(item.amount, item.paid_amount)
        entity_type = "installment"
    else:
        raise HTTPException(status_code=400, detail="نوع السجل غير صحيح.")

    phone_raw = client.phone if client else ""
    phone_clean, phone_error = normalize_phone(phone_raw)
    message = overdue_reminder_message(client.full_name if client else "-", balance, due_date or date.today())
    log_action(
        db,
        user=user,
        action="open_overdue_whatsapp_reminder",
        entity_type=entity_type,
        entity_id=source_id,
        new_value={
            "client_id": client.id if client else None,
            "matter_id": matter.id if matter else None,
            "phone_raw": phone_raw,
            "balance": str(balance),
            "due_date": str(due_date),
            "result": "missing_phone" if not phone_raw else ("invalid_phone" if phone_error else "opened"),
        },
        request=request,
    )
    db.commit()

    if not phone_raw:
        raise HTTPException(status_code=400, detail="لا يوجد رقم هاتف للعميل")
    if phone_error:
        raise HTTPException(status_code=400, detail=phone_error)
    return JSONResponse({"url": whatsapp_url(phone_clean, message)})

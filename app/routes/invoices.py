from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Invoice, Matter, Payment, Task, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date, parse_decimal, setting_value
from app.services.accounting import DATE_STATUS_OPTIONS, date_status_badge, next_number, validate_date_quality
from app.services.audit import log_action
from app.services.auth import ensure_role, get_current_user
from app.services.tasks import generate_automatic_tasks
from app.templating import templates

router = APIRouter(prefix="/invoices", tags=["invoices"])


def refresh_invoice_status(invoice: Invoice) -> None:
    if invoice.paid_amount <= 0:
        invoice.status = "unpaid"
    elif invoice.paid_amount >= invoice.total_amount:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"


def validate_client_matter(db: Session, client_id: int, matter_id: str) -> int | None:
    parsed_matter_id = int_or_none(matter_id)
    if not parsed_matter_id:
        return None
    matter = db.get(Matter, parsed_matter_id)
    if not matter or matter.client_id != client_id:
        raise HTTPException(status_code=400, detail="Selected matter does not belong to the selected client.")
    return parsed_matter_id


@router.get("")
def invoices_index(request: Request, q: str | None = None, status: str | None = None, client_id: str | None = None, date_from: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_client_id = int_or_none(client_id)
    stmt = select(Invoice).options(selectinload(Invoice.client), selectinload(Invoice.matter))
    if q:
        stmt = stmt.where(Invoice.invoice_number.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Invoice.status == status)
    if parsed_client_id:
        stmt = stmt.where(Invoice.client_id == parsed_client_id)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= parse_date(date_from))
    return templates.TemplateResponse("invoices/index.html", {"request": request, "user": user, "invoices": db.scalars(stmt.order_by(Invoice.issue_date.desc())).all(), **get_form_context(db), "filters": {"q": q or "", "status": status or "", "client_id": client_id or "", "date_from": date_from or ""}})


@router.get("/new")
def invoice_new(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"accountant"})
    return templates.TemplateResponse("invoices/form.html", {"request": request, "user": user, "invoice": None, "next_invoice_number": next_number(db, Invoice, "invoice_number", "INV"), **get_form_context(db)})


@router.post("/new")
def invoice_create(request: Request, invoice_number: str = Form(...), client_id: int = Form(...), matter_id: str = Form(""), issue_date: str = Form(...), due_date: str = Form(""), subtotal: str = Form("0"), discount: str = Form("0"), tax: str = Form("0"), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"accountant"})
    parsed_matter_id = validate_client_matter(db, client_id, matter_id)
    invoice_number = invoice_number or next_number(db, Invoice, "invoice_number", "INV")
    subtotal_d = parse_decimal(subtotal)
    discount_d = parse_decimal(discount)
    tax_d = parse_decimal(tax)
    total = subtotal_d - discount_d + tax_d
    invoice = Invoice(invoice_number=invoice_number, client_id=client_id, matter_id=parsed_matter_id, issue_date=parse_date(issue_date) or date.today(), due_date=parse_date(due_date), subtotal=subtotal_d, discount=discount_d, tax=tax_d, total_amount=total, paid_amount=Decimal("0"), status="unpaid", notes=none_if_empty(notes))
    db.add(invoice)
    db.flush()
    log_action(db, user=user, action="create_invoice", entity_type="invoice", entity_id=invoice.id, new_value={"invoice_number": invoice_number}, request=request)
    generate_automatic_tasks(db)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{invoice_id}")
def invoice_detail(request: Request, invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.client), selectinload(Invoice.matter), selectinload(Invoice.payments)))
    whatsapp_text = f"فاتورة {invoice.invoice_number} من مكتب سعيد الشبيبي للمحاماة، الإجمالي: {invoice.total_amount}"
    return templates.TemplateResponse("invoices/detail.html", {"request": request, "user": user, "invoice": invoice, "whatsapp_text": whatsapp_text, "date_status_options": DATE_STATUS_OPTIONS, "date_status_badge": date_status_badge})


@router.post("/{invoice_id}/payments")
def payment_create(request: Request, invoice_id: int, amount: str = Form(...), payment_date: str = Form(""), date_status: str = Form("confirmed"), date_note: str = Form(""), method: str = Form("cash"), reference_no: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"accountant"})
    try:
        date_status_value, date_note_value, payment_date_value = validate_date_quality(date_status, date_note, parse_date(payment_date))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة.")
    payment_amount = parse_decimal(amount)
    if payment_amount <= 0:
        raise HTTPException(status_code=400, detail="مبلغ الدفعة يجب أن يكون أكبر من صفر.")
    remaining = (invoice.total_amount or Decimal("0")) - (invoice.paid_amount or Decimal("0"))
    if remaining <= 0 or invoice.status == "paid":
        raise HTTPException(status_code=400, detail="هذه الفاتورة مدفوعة بالكامل، ولا يمكن تسجيل دفعة أخرى.")
    if payment_amount > remaining:
        raise HTTPException(status_code=400, detail=f"المبلغ أكبر من المتبقي على الفاتورة. المتبقي: {remaining:.2f}")
    payment = Payment(invoice_id=invoice.id, amount=payment_amount, payment_date=payment_date_value, date_status=date_status_value, date_note=date_note_value, method=method, reference_no=none_if_empty(reference_no), notes=none_if_empty(notes))
    invoice.paid_amount = (invoice.paid_amount or Decimal("0")) + payment_amount
    refresh_invoice_status(invoice)
    if invoice.status == "paid":
        for task in db.scalars(select(Task).where(Task.invoice_id == invoice.id, Task.status != "completed")).all():
            task.status = "completed"
            task.completed_at = datetime.now()
    db.add(payment)
    db.flush()
    log_action(db, user=user, action="create_payment", entity_type="payment", entity_id=payment.id, new_value={"invoice_id": invoice.id, "amount": str(payment_amount)}, request=request)
    db.commit()
    return RedirectResponse(f"/invoices/{invoice.id}", status_code=303)


@router.get("/{invoice_id}/print")
def invoice_print(request: Request, invoice_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.client), selectinload(Invoice.matter), selectinload(Invoice.payments)))
    return templates.TemplateResponse("invoices/print.html", {"request": request, "user": user, "invoice": invoice, "office_name": setting_value(db, "office_name", "مكتب سعيد الشبيبي للمحاماة"), "invoice_footer": setting_value(db, "invoice_footer", "")})

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Client, Invoice, Payment, ReceiptVoucher, User
from app.routes.helpers import int_or_none
from app.services.accounting import DATE_STATUS_OPTIONS, date_status_badge
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("")
def payments_index(request: Request, client_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"accountant"})
    parsed_client_id = int_or_none(client_id)
    payment_stmt = (
        select(Payment)
        .join(Invoice)
        .options(selectinload(Payment.invoice).selectinload(Invoice.client), selectinload(Payment.invoice).selectinload(Invoice.matter))
        .order_by(Payment.payment_date.desc())
    )
    receipt_stmt = (
        select(ReceiptVoucher)
        .options(selectinload(ReceiptVoucher.client), selectinload(ReceiptVoucher.invoice), selectinload(ReceiptVoucher.matter), selectinload(ReceiptVoucher.case_fee))
        .where(ReceiptVoucher.status == "active")
        .order_by(ReceiptVoucher.received_at.desc(), ReceiptVoucher.created_at.desc())
    )
    if parsed_client_id:
        payment_stmt = payment_stmt.where(Invoice.client_id == parsed_client_id)
        receipt_stmt = receipt_stmt.where(ReceiptVoucher.client_id == parsed_client_id)
    rows = []
    for payment in db.scalars(payment_stmt).all():
        invoice = payment.invoice
        rows.append(
            {
                "date": payment.payment_date,
                "client": invoice.client.full_name if invoice and invoice.client else "-",
                "source_type": "فاتورة",
                "source_number": invoice.invoice_number if invoice else "-",
                "source_url": f"/invoices/{payment.invoice_id}" if payment.invoice_id else "",
                "amount": payment.amount,
                "method": payment.method,
                "reference_no": payment.reference_no,
                "date_status": payment.date_status,
                "date_note": payment.date_note,
                "action_type": "whatsapp",
                "action_id": payment.id,
            }
        )
    for receipt in db.scalars(receipt_stmt).all():
        receipt_type = receipt.receipt_type or ("invoice" if receipt.invoice else "case_fee")
        source_type = "سند قبض أتعاب" if receipt_type == "case_fee" else "سند قبض فاتورة"
        if receipt_type == "general":
            source_type = "سند قبض عام"
        source_number = receipt.receipt_number
        if receipt.invoice:
            source_number = f"{receipt.receipt_number} / {receipt.invoice.invoice_number}"
        rows.append(
            {
                "date": receipt.received_at,
                "client": receipt.client.full_name if receipt.client else "-",
                "source_type": source_type,
                "source_number": source_number,
                "source_url": f"/accounting/receipts/{receipt.id}/print",
                "amount": receipt.amount,
                "method": receipt.payment_method,
                "reference_no": receipt.reference_no,
                "date_status": receipt.date_status,
                "date_note": receipt.date_note,
                "action_type": "print",
                "action_id": receipt.id,
            }
        )
    rows.sort(key=lambda row: row["date"], reverse=True)
    return templates.TemplateResponse(
        "payments/index.html",
        {
            "request": request,
            "user": user,
            "payment_rows": rows,
            "clients": db.scalars(select(Client).order_by(Client.full_name)).all(),
            "client_id": client_id or "",
            "date_status_options": DATE_STATUS_OPTIONS,
            "date_status_badge": date_status_badge,
        },
    )

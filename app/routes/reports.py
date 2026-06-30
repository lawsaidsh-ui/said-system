import csv
import io
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, CourtSession, Invoice, Matter, Payment, User
from app.services.auth import get_current_user
from app.templating import templates

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def reports_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today = date.today()
    month_start = today.replace(day=1)
    data = {
        "matters_by_status": db.execute(select(Matter.status, func.count(Matter.id)).group_by(Matter.status)).all(),
        "upcoming_sessions": db.scalars(select(CourtSession).where(CourtSession.session_date >= today).order_by(CourtSession.session_date).limit(20)).all(),
        "new_clients": db.scalars(select(Client).where(Client.created_at >= today - timedelta(days=30)).order_by(Client.created_at.desc())).all(),
        "unpaid_invoices": db.scalars(select(Invoice).where(Invoice.status.in_(["unpaid", "partially_paid"])).order_by(Invoice.due_date)).all(),
        "monthly_revenue": db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.payment_date >= month_start)),
        "lawyer_performance": db.execute(select(User.full_name, func.count(Matter.id)).join(Matter, Matter.assigned_lawyer_id == User.id).where(User.role.in_(["lawyer", "admin"])).group_by(User.full_name)).all(),
    }
    return templates.TemplateResponse("reports/index.html", {"request": request, "user": user, **data})


@router.get("/export/{report_name}.csv")
def export_csv(report_name: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    output = io.StringIO()
    writer = csv.writer(output)
    if report_name == "unpaid_invoices":
        writer.writerow(["invoice_number", "client_id", "total_amount", "paid_amount", "status"])
        for invoice in db.scalars(select(Invoice).where(Invoice.status.in_(["unpaid", "partially_paid"]))):
            writer.writerow([invoice.invoice_number, invoice.client_id, invoice.total_amount, invoice.paid_amount, invoice.status])
    else:
        writer.writerow(["status", "count"])
        for status, count in db.execute(select(Matter.status, func.count(Matter.id)).group_by(Matter.status)):
            writer.writerow([status, count])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_name}.csv"})

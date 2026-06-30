from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Consultation, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date, parse_decimal
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/consultations", tags=["consultations"])


@router.get("")
def consultations_index(request: Request, status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Consultation).options(selectinload(Consultation.client), selectinload(Consultation.assigned_lawyer))
    if status:
        stmt = stmt.where(Consultation.status == status)
    return templates.TemplateResponse("consultations/index.html", {"request": request, "user": user, "consultations": db.scalars(stmt.order_by(Consultation.created_at.desc())).all(), "status": status or ""})


@router.get("/new")
def consultation_new(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    return templates.TemplateResponse("consultations/form.html", {"request": request, "user": user, "consultation": None, **get_form_context(db)})


@router.post("/new")
def consultation_create(request: Request, client_id: str = Form(""), requester_name: str = Form(...), requester_phone: str = Form(...), requester_email: str = Form(""), consultation_type: str = Form(""), subject: str = Form(...), description: str = Form(""), status: str = Form("new"), assigned_lawyer_id: str = Form(""), consultation_date: str = Form(""), fee_amount: str = Form("0"), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    item = Consultation(client_id=int_or_none(client_id), requester_name=requester_name, requester_phone=requester_phone, requester_email=none_if_empty(requester_email), consultation_type=none_if_empty(consultation_type), subject=subject, description=none_if_empty(description), status=status, assigned_lawyer_id=int_or_none(assigned_lawyer_id), consultation_date=parse_date(consultation_date), fee_amount=parse_decimal(fee_amount), notes=none_if_empty(notes))
    db.add(item)
    db.commit()
    return RedirectResponse("/consultations", status_code=303)


@router.get("/{consultation_id}")
def consultation_detail(request: Request, consultation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    consultation = db.scalar(select(Consultation).where(Consultation.id == consultation_id).options(selectinload(Consultation.client), selectinload(Consultation.assigned_lawyer)))
    return templates.TemplateResponse("consultations/detail.html", {"request": request, "user": user, "consultation": consultation})

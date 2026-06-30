from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Appointment, User
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
def appointments_index(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"secretary", "lawyer", "accountant", "data_entry"})
    stmt = select(Appointment)
    if status:
        stmt = stmt.where(Appointment.status == status)
    appointments = db.scalars(stmt.order_by(Appointment.appointment_date.desc(), Appointment.appointment_time.desc())).all()
    statuses = db.scalars(select(Appointment.status)).all()
    appointment_counts = {
        "all": len(statuses),
        "pending": statuses.count("pending"),
        "confirmed": statuses.count("confirmed"),
        "completed": statuses.count("completed"),
        "cancelled": statuses.count("cancelled"),
    }
    return templates.TemplateResponse(
        "appointments/index.html",
        {
            "request": request,
            "user": user,
            "appointments": appointments,
            "appointment_counts": appointment_counts,
            "status": status or "",
        },
    )


@router.post("/{appointment_id}/status")
def appointment_status_update(
    request: Request,
    appointment_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"secretary", "lawyer", "data_entry"})
    appointment = db.get(Appointment, appointment_id)
    appointment.status = status
    db.commit()
    return RedirectResponse("/appointments", status_code=303)

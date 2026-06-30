from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import CourtSession, Matter, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date, parse_time
from app.services.audit import log_action
from app.services.auth import ensure_role, get_current_user
from app.services.tasks import generate_automatic_tasks
from app.templating import templates

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
def sessions_index(request: Request, date_from: str | None = None, court: str | None = None, status: str | None = None, lawyer_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_lawyer_id = int_or_none(lawyer_id)
    stmt = select(CourtSession).join(Matter).options(selectinload(CourtSession.matter).selectinload(Matter.assigned_lawyer), selectinload(CourtSession.matter).selectinload(Matter.client))
    if date_from:
        stmt = stmt.where(CourtSession.session_date >= parse_date(date_from))
    if court:
        stmt = stmt.where(CourtSession.court_name.ilike(f"%{court}%"))
    if status:
        stmt = stmt.where(CourtSession.session_status == status)
    if parsed_lawyer_id:
        stmt = stmt.where(Matter.assigned_lawyer_id == parsed_lawyer_id)
    sessions = db.scalars(stmt.order_by(CourtSession.session_date, CourtSession.session_time)).all()
    return templates.TemplateResponse("sessions/index.html", {"request": request, "user": user, "sessions": sessions, "today": date.today(), **get_form_context(db), "filters": {"date_from": date_from or "", "court": court or "", "status": status or "", "lawyer_id": lawyer_id or ""}})


@router.get("/new")
def session_new(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    return templates.TemplateResponse("sessions/form.html", {"request": request, "user": user, "session": None, **get_form_context(db)})


@router.post("/new")
def session_create(request: Request, matter_id: int = Form(...), session_date: str = Form(...), session_time: str = Form(""), court_name: str = Form(...), hall_number: str = Form(""), judge_name: str = Form(""), session_status: str = Form("scheduled"), decision_summary: str = Form(""), next_action: str = Form(""), next_session_date: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    item = CourtSession(matter_id=matter_id, session_date=parse_date(session_date), session_time=parse_time(session_time), court_name=court_name, hall_number=none_if_empty(hall_number), judge_name=none_if_empty(judge_name), session_status=session_status, decision_summary=none_if_empty(decision_summary), next_action=none_if_empty(next_action), next_session_date=parse_date(next_session_date), notes=none_if_empty(notes))
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_session", entity_type="court_session", entity_id=item.id, new_value={"matter_id": matter_id}, request=request)
    generate_automatic_tasks(db)
    db.commit()
    return RedirectResponse("/sessions", status_code=303)


@router.get("/{session_id}/edit")
def session_edit(request: Request, session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    return templates.TemplateResponse("sessions/form.html", {"request": request, "user": user, "session": db.get(CourtSession, session_id), **get_form_context(db)})


@router.post("/{session_id}/edit")
def session_update(request: Request, session_id: int, matter_id: int = Form(...), session_date: str = Form(...), session_time: str = Form(""), court_name: str = Form(...), hall_number: str = Form(""), judge_name: str = Form(""), session_status: str = Form("scheduled"), decision_summary: str = Form(""), next_action: str = Form(""), next_session_date: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    item = db.get(CourtSession, session_id)
    old = {"session_date": item.session_date, "status": item.session_status}
    item.matter_id = matter_id
    item.session_date = parse_date(session_date)
    item.session_time = parse_time(session_time)
    item.court_name = court_name
    item.hall_number = none_if_empty(hall_number)
    item.judge_name = none_if_empty(judge_name)
    item.session_status = session_status
    item.decision_summary = none_if_empty(decision_summary)
    item.next_action = none_if_empty(next_action)
    item.next_session_date = parse_date(next_session_date)
    item.notes = none_if_empty(notes)
    log_action(db, user=user, action="update_session", entity_type="court_session", entity_id=item.id, old_value=old, new_value={"status": session_status}, request=request)
    generate_automatic_tasks(db)
    db.commit()
    return RedirectResponse("/sessions", status_code=303)

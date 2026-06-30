from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Client, Document, Matter, User
from app.routes.helpers import find_similar_client, get_form_context, int_or_none, none_if_empty, parse_date, parse_decimal
from app.services.audit import audit_logs_for_targets, log_action
from app.services.auth import ensure_role, get_current_user
from app.services.tasks import create_matter_status_change_task, generate_automatic_tasks
from app.templating import templates

router = APIRouter(prefix="/matters", tags=["matters"])


def next_office_case_number(db: Session) -> str:
    year = date.today().year
    total = db.scalar(select(func.count(Matter.id))) or 0
    sequence = total + 1
    while True:
        candidate = f"OFF-{year}-{sequence:04d}"
        exists = db.scalar(select(Matter.id).where(Matter.case_number == candidate))
        if not exists:
            return candidate
        sequence += 1


@router.get("")
def matters_index(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    lawyer_id: str | None = None,
    court: str | None = None,
    case_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_lawyer_id = int_or_none(lawyer_id)
    stmt = select(Matter).join(Client).options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Matter.case_number.ilike(like),
                Matter.ministry_case_number.ilike(like),
                Matter.title.ilike(like),
                Client.full_name.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(Matter.status == status)
    if parsed_lawyer_id:
        stmt = stmt.where(Matter.assigned_lawyer_id == parsed_lawyer_id)
    if court:
        stmt = stmt.where(Matter.court_name.ilike(f"%{court}%"))
    if case_type:
        stmt = stmt.where(Matter.case_type.ilike(f"%{case_type}%"))
    matters = db.scalars(stmt.order_by(Matter.created_at.desc())).all()
    return templates.TemplateResponse("matters/index.html", {"request": request, "user": user, "matters": matters, **get_form_context(db), "filters": {"q": q or "", "status": status or "", "lawyer_id": lawyer_id or "", "court": court or "", "case_type": case_type or ""}})


@router.get("/new")
def matter_new(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    return templates.TemplateResponse("matters/form.html", {"request": request, "user": user, "matter": None, **get_form_context(db)})


@router.post("/new")
def matter_create(
    request: Request,
    case_number: str = Form(""),
    ministry_case_number: str = Form(""),
    title: str = Form(...),
    client_mode: str = Form("existing"),
    client_id: str = Form(""),
    new_client_full_name: str = Form(""),
    new_client_phone: str = Form(""),
    new_client_email: str = Form(""),
    new_client_civil_id: str = Form(""),
    new_client_type: str = Form("individual"),
    new_client_company_name: str = Form(""),
    new_client_commercial_registration: str = Form(""),
    new_client_address: str = Form(""),
    new_client_notes: str = Form(""),
    assigned_lawyer_id: str = Form(""),
    case_type: str = Form(""),
    court_name: str = Form(""),
    court_level: str = Form(""),
    opponent_name: str = Form(""),
    opponent_phone: str = Form(""),
    status: str = Form("new"),
    priority: str = Form("medium"),
    description: str = Form(""),
    claim_amount: str = Form("0"),
    opened_at: str = Form(""),
    closed_at: str = Form(""),
    appeal_deadline: str = Form(""),
    cassation_deadline: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    if client_mode == "new":
        if not new_client_full_name.strip():
            return templates.TemplateResponse(
                "matters/form.html",
                {
                    "request": request,
                    "user": user,
                    "matter": None,
                    "error": "اكتب اسم العميل الجديد قبل حفظ القضية.",
                    **get_form_context(db),
                },
                status_code=400,
            )
        is_company = new_client_type == "company"
        client = find_similar_client(
            db,
            new_client_full_name,
            phone=none_if_empty(new_client_phone),
            civil_id=None if is_company else none_if_empty(new_client_civil_id),
            commercial_registration=none_if_empty(new_client_commercial_registration) if is_company else None,
        )
        if not client:
            client = Client(
                full_name=new_client_full_name,
                phone=none_if_empty(new_client_phone),
                email=none_if_empty(new_client_email),
                civil_id=None if is_company else none_if_empty(new_client_civil_id),
                address=none_if_empty(new_client_address),
                client_type=new_client_type,
                company_name=none_if_empty(new_client_company_name) if is_company else None,
                commercial_registration=none_if_empty(new_client_commercial_registration) if is_company else None,
                notes=none_if_empty(new_client_notes),
            )
            db.add(client)
            db.flush()
            log_action(
                db,
                user=user,
                action="create_client",
                entity_type="client",
                entity_id=client.id,
                new_value={"full_name": client.full_name, "source": "matter_create"},
                request=request,
            )
        matter_client_id = client.id
    else:
        matter_client_id = int_or_none(client_id)
        if not matter_client_id:
            return templates.TemplateResponse(
                "matters/form.html",
                {
                    "request": request,
                    "user": user,
                    "matter": None,
                    "error": "اختر عميلاً موجوداً أو فعّل خيار إضافة عميل جديد.",
                    **get_form_context(db),
                },
                status_code=400,
            )

    office_case_number = none_if_empty(case_number) or next_office_case_number(db)
    matter = Matter(
        case_number=office_case_number,
        ministry_case_number=none_if_empty(ministry_case_number),
        title=title,
        client_id=matter_client_id,
        assigned_lawyer_id=int_or_none(assigned_lawyer_id),
        case_type=none_if_empty(case_type),
        court_name=none_if_empty(court_name),
        court_level=none_if_empty(court_level),
        opponent_name=none_if_empty(opponent_name),
        opponent_phone=none_if_empty(opponent_phone),
        status=status,
        priority=priority,
        description=none_if_empty(description),
        claim_amount=parse_decimal(claim_amount),
        opened_at=parse_date(opened_at),
        closed_at=parse_date(closed_at),
        appeal_deadline=parse_date(appeal_deadline),
        cassation_deadline=parse_date(cassation_deadline),
    )
    db.add(matter)
    db.flush()
    log_action(
        db,
        user=user,
        action="create_matter",
        entity_type="matter",
        entity_id=matter.id,
        new_value={"case_number": office_case_number, "ministry_case_number": matter.ministry_case_number},
        request=request,
    )
    generate_automatic_tasks(db)
    db.commit()
    return RedirectResponse(f"/matters/{matter.id}", status_code=303)


@router.get("/{matter_id}")
def matter_detail(request: Request, matter_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    matter = db.scalar(
        select(Matter)
        .where(Matter.id == matter_id)
        .options(
            selectinload(Matter.client),
            selectinload(Matter.assigned_lawyer),
            selectinload(Matter.sessions),
            selectinload(Matter.tasks),
            selectinload(Matter.documents).selectinload(Document.uploaded_by),
            selectinload(Matter.invoices),
        )
    )
    audit_logs = []
    if user.role == "admin":
        document_ids = [document.id for document in matter.documents]
        audit_logs = audit_logs_for_targets(
            db,
            [("matter", matter.id)] + [("document", document_id) for document_id in document_ids],
        )
    return templates.TemplateResponse(
        "matters/detail.html",
        {"request": request, "user": user, "matter": matter, "audit_logs": audit_logs},
    )


@router.get("/{matter_id}/edit")
def matter_edit(request: Request, matter_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    return templates.TemplateResponse("matters/form.html", {"request": request, "user": user, "matter": db.get(Matter, matter_id), **get_form_context(db)})


@router.post("/{matter_id}/edit")
def matter_update(
    request: Request,
    matter_id: int,
    case_number: str = Form(...),
    ministry_case_number: str = Form(""),
    title: str = Form(...),
    client_id: int = Form(...),
    assigned_lawyer_id: str = Form(""),
    case_type: str = Form(""),
    court_name: str = Form(""),
    court_level: str = Form(""),
    opponent_name: str = Form(""),
    opponent_phone: str = Form(""),
    status: str = Form("new"),
    priority: str = Form("medium"),
    description: str = Form(""),
    claim_amount: str = Form("0"),
    opened_at: str = Form(""),
    closed_at: str = Form(""),
    appeal_deadline: str = Form(""),
    cassation_deadline: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    matter = db.get(Matter, matter_id)
    old = {
        "status": matter.status,
        "assigned_lawyer_id": matter.assigned_lawyer_id,
        "case_number": matter.case_number,
        "ministry_case_number": matter.ministry_case_number,
    }
    matter.case_number = case_number
    matter.ministry_case_number = none_if_empty(ministry_case_number)
    matter.title = title
    matter.client_id = client_id
    matter.assigned_lawyer_id = int_or_none(assigned_lawyer_id)
    matter.case_type = none_if_empty(case_type)
    matter.court_name = none_if_empty(court_name)
    matter.court_level = none_if_empty(court_level)
    matter.opponent_name = none_if_empty(opponent_name)
    matter.opponent_phone = none_if_empty(opponent_phone)
    matter.status = status
    matter.priority = priority
    matter.description = none_if_empty(description)
    matter.claim_amount = parse_decimal(claim_amount)
    matter.opened_at = parse_date(opened_at)
    matter.closed_at = parse_date(closed_at)
    matter.appeal_deadline = parse_date(appeal_deadline)
    matter.cassation_deadline = parse_date(cassation_deadline)
    action = "close_matter" if old["status"] != "closed" and status == "closed" else "update_matter"
    log_action(
        db,
        user=user,
        action=action,
        entity_type="matter",
        entity_id=matter.id,
        old_value=old,
        new_value={"status": status, "case_number": matter.case_number, "ministry_case_number": matter.ministry_case_number},
        request=request,
    )
    create_matter_status_change_task(db, matter=matter, old_status=old["status"], new_status=status)
    db.commit()
    return RedirectResponse(f"/matters/{matter.id}", status_code=303)

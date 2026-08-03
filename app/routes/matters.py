from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Client, Document, Matter, User
from app.routes.helpers import can_see_document, find_similar_client, get_form_context, int_or_none, none_if_empty, pagination_context, parse_date, parse_decimal, save_upload
from app.services.audit import audit_logs_for_targets, log_action
from app.services.auth import ensure_role, get_current_user
from app.services.tasks import create_matter_status_change_task, generate_automatic_tasks
from app.templating import templates

router = APIRouter(prefix="/matters", tags=["matters"])


def matter_text_key(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def matter_duplicate_signature(
    *,
    client_id: int,
    title: str,
    ministry_case_number: str | None,
    case_type: str | None,
    court_name: str | None,
    opponent_name: str | None,
    opened_at: date | None,
    claim_amount,
) -> tuple:
    ministry_key = matter_text_key(ministry_case_number)
    if ministry_key:
        return ("ministry", ministry_key)
    return (
        "manual",
        client_id,
        matter_text_key(title),
        matter_text_key(case_type),
        matter_text_key(court_name),
        matter_text_key(opponent_name),
        opened_at.isoformat() if opened_at else "",
        str(claim_amount or "0"),
    )


def find_duplicate_matter(
    db: Session,
    *,
    client_id: int,
    title: str,
    ministry_case_number: str | None,
    case_type: str | None,
    court_name: str | None,
    opponent_name: str | None,
    opened_at: date | None,
    claim_amount,
    exclude_matter_id: int | None = None,
) -> Matter | None:
    signature = matter_duplicate_signature(
        client_id=client_id,
        title=title,
        ministry_case_number=ministry_case_number,
        case_type=case_type,
        court_name=court_name,
        opponent_name=opponent_name,
        opened_at=opened_at,
        claim_amount=claim_amount,
    )
    stmt = select(Matter).order_by(Matter.id)
    if signature[0] != "ministry":
        stmt = stmt.where(Matter.client_id == client_id)
    if exclude_matter_id:
        stmt = stmt.where(Matter.id != exclude_matter_id)
    for matter in db.scalars(stmt).all():
        existing_signature = matter_duplicate_signature(
            client_id=matter.client_id,
            title=matter.title,
            ministry_case_number=matter.ministry_case_number,
            case_type=matter.case_type,
            court_name=matter.court_name,
            opponent_name=matter.opponent_name,
            opened_at=matter.opened_at,
            claim_amount=matter.claim_amount,
        )
        if existing_signature == signature:
            return matter
    return None


def find_existing_matter_number(
    db: Session,
    *,
    case_number: str | None = None,
    ministry_case_number: str | None = None,
    exclude_matter_id: int | None = None,
) -> Matter | None:
    normalized_case_number = matter_text_key(case_number)
    normalized_ministry_case_number = matter_text_key(ministry_case_number)
    if not normalized_case_number and not normalized_ministry_case_number:
        return None
    stmt = select(Matter).order_by(Matter.id)
    if exclude_matter_id:
        stmt = stmt.where(Matter.id != exclude_matter_id)
    for matter in db.scalars(stmt).all():
        if normalized_case_number and matter_text_key(matter.case_number) == normalized_case_number:
            return matter
        if normalized_ministry_case_number and matter_text_key(matter.ministry_case_number) == normalized_ministry_case_number:
            return matter
    return None


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
    page: int = 1,
    all: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    per_page = 25
    show_all = all == "1"
    parsed_lawyer_id = int_or_none(lawyer_id)
    stmt = select(Matter).join(Client).options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
    count_stmt = select(func.count(Matter.id)).join(Client)
    if q:
        like = f"%{q}%"
        search_filter = or_(
            cast(Matter.id, String).ilike(like),
            Matter.case_number.ilike(like),
            Matter.ministry_case_number.ilike(like),
            Matter.title.ilike(like),
            Client.full_name.ilike(like),
            cast(Client.id, String).ilike(like),
            Client.phone.ilike(like),
            Client.civil_id.ilike(like),
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)
    if status:
        stmt = stmt.where(Matter.status == status)
        count_stmt = count_stmt.where(Matter.status == status)
    if parsed_lawyer_id:
        stmt = stmt.where(Matter.assigned_lawyer_id == parsed_lawyer_id)
        count_stmt = count_stmt.where(Matter.assigned_lawyer_id == parsed_lawyer_id)
    if court:
        stmt = stmt.where(Matter.court_name.ilike(f"%{court}%"))
        count_stmt = count_stmt.where(Matter.court_name.ilike(f"%{court}%"))
    if case_type:
        stmt = stmt.where(Matter.case_type.ilike(f"%{case_type}%"))
        count_stmt = count_stmt.where(Matter.case_type.ilike(f"%{case_type}%"))

    total_matters = db.scalar(count_stmt) or 0
    pagination = pagination_context(request, total=total_matters, page=page, per_page=per_page, show_all=show_all)
    stmt = stmt.order_by(Matter.created_at.desc(), Matter.id.desc())
    if not show_all:
        stmt = stmt.limit(per_page).offset((pagination["page"] - 1) * per_page)
    matters = db.scalars(stmt).all()
    context = get_form_context(db)
    context["matters"] = matters
    context["matter_count"] = len(matters)
    context["total_matters"] = total_matters
    context["pagination"] = pagination
    context["filters"] = {
        "q": q or "",
        "status": status or "",
        "lawyer_id": lawyer_id or "",
        "court": court or "",
        "case_type": case_type or "",
    }
    return templates.TemplateResponse("matters/index.html", {"request": request, "user": user, **context})


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

    normalized_ministry_case_number = none_if_empty(ministry_case_number)
    normalized_case_type = none_if_empty(case_type)
    normalized_court_name = none_if_empty(court_name)
    normalized_opponent_name = none_if_empty(opponent_name)
    parsed_claim_amount = parse_decimal(claim_amount)
    parsed_opened_at = parse_date(opened_at)
    parsed_closed_at = parse_date(closed_at)
    parsed_appeal_deadline = parse_date(appeal_deadline)
    parsed_cassation_deadline = parse_date(cassation_deadline)

    duplicate_matter = find_existing_matter_number(
        db,
        case_number=none_if_empty(case_number),
        ministry_case_number=normalized_ministry_case_number,
    ) or find_duplicate_matter(
        db,
        client_id=matter_client_id,
        title=title,
        ministry_case_number=normalized_ministry_case_number,
        case_type=normalized_case_type,
        court_name=normalized_court_name,
        opponent_name=normalized_opponent_name,
        opened_at=parsed_opened_at,
        claim_amount=parsed_claim_amount,
    )
    if duplicate_matter:
        return RedirectResponse(f"/matters/{duplicate_matter.id}", status_code=303)

    office_case_number = none_if_empty(case_number) or next_office_case_number(db)
    matter = Matter(
        case_number=office_case_number,
        ministry_case_number=normalized_ministry_case_number,
        title=title,
        client_id=matter_client_id,
        assigned_lawyer_id=int_or_none(assigned_lawyer_id),
        case_type=normalized_case_type,
        court_name=normalized_court_name,
        court_level=none_if_empty(court_level),
        opponent_name=normalized_opponent_name,
        opponent_phone=none_if_empty(opponent_phone),
        status=status,
        priority=priority,
        description=none_if_empty(description),
        claim_amount=parsed_claim_amount,
        opened_at=parsed_opened_at,
        closed_at=parsed_closed_at,
        appeal_deadline=parsed_appeal_deadline,
        cassation_deadline=parsed_cassation_deadline,
    )
    db.add(matter)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        duplicate_matter = find_duplicate_matter(
            db,
            client_id=matter_client_id,
            title=title,
            ministry_case_number=normalized_ministry_case_number,
            case_type=normalized_case_type,
            court_name=normalized_court_name,
            opponent_name=normalized_opponent_name,
            opened_at=parsed_opened_at,
            claim_amount=parsed_claim_amount,
        )
        if duplicate_matter:
            return RedirectResponse(f"/matters/{duplicate_matter.id}", status_code=303)
        raise
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
    matter_documents = [document for document in matter.documents if can_see_document(user, document)]
    if user.role == "admin":
        document_ids = [document.id for document in matter_documents]
        audit_logs = audit_logs_for_targets(
            db,
            [("matter", matter.id)] + [("document", document_id) for document_id in document_ids],
        )
    return templates.TemplateResponse(
        "matters/detail.html",
        {"request": request, "user": user, "matter": matter, "matter_documents": matter_documents, "audit_logs": audit_logs},
    )


@router.post("/{matter_id}/documents")
async def matter_document_upload(
    request: Request,
    matter_id: int,
    title: str = Form(...),
    document_type: str = Form(""),
    notes: str = Form(""),
    is_confidential: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    matter = db.get(Matter, matter_id)
    if not matter:
        return RedirectResponse("/matters", status_code=303)
    file_url, file_name, file_size, mime_type = await save_upload(file)
    document = Document(
        title=title,
        document_type=none_if_empty(document_type),
        client_id=matter.client_id,
        matter_id=matter.id,
        uploaded_by_id=user.id,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        notes=none_if_empty(notes),
        is_confidential=bool(is_confidential),
    )
    db.add(document)
    db.flush()
    log_action(
        db,
        user=user,
        action="upload_document",
        entity_type="document",
        entity_id=document.id,
        new_value={
            "title": title,
            "file_name": file_name,
            "client_id": document.client_id,
            "matter_id": document.matter_id,
            "source": "matter_detail",
        },
        request=request,
    )
    db.commit()
    return RedirectResponse(f"/matters/{matter.id}#documents", status_code=303)


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
    normalized_ministry_case_number = none_if_empty(ministry_case_number)
    normalized_case_type = none_if_empty(case_type)
    normalized_court_name = none_if_empty(court_name)
    normalized_opponent_name = none_if_empty(opponent_name)
    parsed_claim_amount = parse_decimal(claim_amount)
    parsed_opened_at = parse_date(opened_at)
    parsed_closed_at = parse_date(closed_at)
    parsed_appeal_deadline = parse_date(appeal_deadline)
    parsed_cassation_deadline = parse_date(cassation_deadline)
    duplicate_matter = find_existing_matter_number(
        db,
        case_number=case_number,
        ministry_case_number=normalized_ministry_case_number,
        exclude_matter_id=matter_id,
    ) or find_duplicate_matter(
        db,
        client_id=client_id,
        title=title,
        ministry_case_number=normalized_ministry_case_number,
        case_type=normalized_case_type,
        court_name=normalized_court_name,
        opponent_name=normalized_opponent_name,
        opened_at=parsed_opened_at,
        claim_amount=parsed_claim_amount,
        exclude_matter_id=matter_id,
    )
    if duplicate_matter:
        return RedirectResponse(f"/matters/{duplicate_matter.id}", status_code=303)

    matter.case_number = case_number
    matter.ministry_case_number = normalized_ministry_case_number
    matter.title = title
    matter.client_id = client_id
    matter.assigned_lawyer_id = int_or_none(assigned_lawyer_id)
    matter.case_type = normalized_case_type
    matter.court_name = normalized_court_name
    matter.court_level = none_if_empty(court_level)
    matter.opponent_name = normalized_opponent_name
    matter.opponent_phone = none_if_empty(opponent_phone)
    matter.status = status
    matter.priority = priority
    matter.description = none_if_empty(description)
    matter.claim_amount = parsed_claim_amount
    matter.opened_at = parsed_opened_at
    matter.closed_at = parsed_closed_at
    matter.appeal_deadline = parsed_appeal_deadline
    matter.cassation_deadline = parsed_cassation_deadline
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

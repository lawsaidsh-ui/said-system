from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Agency, Client, Matter, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date
from app.services.audit import log_action
from app.services.auth import require_roles
from app.templating import templates

router = APIRouter(prefix="/agencies", tags=["agencies"])

AGENCY_STATUSES = {
    "active": "سارية",
    "expired": "منتهية",
    "cancelled": "ملغاة",
    "pending": "قيد الإجراء",
}


def _agency_context(db: Session, **extra) -> dict:
    return {
        **get_form_context(db),
        "agency_statuses": AGENCY_STATUSES,
        **extra,
    }


def _validate_matter(db: Session, client_id: int, matter_id: str) -> int | None:
    parsed_matter_id = int_or_none(matter_id)
    if not parsed_matter_id:
        return None
    matter = db.get(Matter, parsed_matter_id)
    if not matter or matter.client_id != client_id:
        raise HTTPException(status_code=400, detail="القضية المختارة لا تتبع العميل المختار.")
    return parsed_matter_id


def _get_agency(db: Session, agency_id: int) -> Agency:
    agency = db.scalar(
        select(Agency)
        .where(Agency.id == agency_id)
        .options(selectinload(Agency.client), selectinload(Agency.matter))
    )
    if not agency:
        raise HTTPException(status_code=404, detail="الوكالة غير موجودة")
    return agency


@router.get("")
def agencies_index(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    stmt = select(Agency).options(selectinload(Agency.client), selectinload(Agency.matter))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Agency.agency_number.ilike(like),
                Agency.title.ilike(like),
                Agency.authorized_person.ilike(like),
                Agency.client.has(Client.full_name.ilike(like)),
            )
        )
    if status:
        stmt = stmt.where(Agency.status == status)
    agencies = db.scalars(stmt.order_by(Agency.created_at.desc(), Agency.id.desc())).all()
    return templates.TemplateResponse(
        "agencies/index.html",
        _agency_context(db, request=request, user=user, agencies=agencies, q=q or "", status=status or ""),
    )


@router.get("/new")
def agency_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse(
        "agencies/form.html",
        _agency_context(db, request=request, user=user, agency=None),
    )


@router.post("/new")
def agency_create(
    request: Request,
    agency_number: str = Form(...),
    title: str = Form(...),
    client_id: str = Form(""),
    matter_id: str = Form(""),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    status: str = Form("active"),
    notary_office: str = Form(""),
    authorized_person: str = Form(""),
    scope: str = Form(""),
    notes: str = Form(""),
    new_client_name: str = Form(""),
    new_client_phone: str = Form(""),
    new_client_email: str = Form(""),
    new_client_civil_id: str = Form(""),
    new_client_type: str = Form("individual"),
    new_client_address: str = Form(""),
    new_client_notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    agency_number = agency_number.strip()
    existing = db.scalar(select(Agency).where(Agency.agency_number == agency_number))
    if existing:
        return templates.TemplateResponse(
            "agencies/form.html",
            _agency_context(db, request=request, user=user, agency=None, error="رقم الوكالة مسجل مسبقاً."),
            status_code=400,
        )

    # Create new client inline if name is provided
    if new_client_name.strip():
        new_client = Client(
            full_name=new_client_name.strip(),
            phone=none_if_empty(new_client_phone),
            email=none_if_empty(new_client_email),
            civil_id=none_if_empty(new_client_civil_id),
            client_type=new_client_type if new_client_type in ("individual", "company") else "individual",
            address=none_if_empty(new_client_address),
            notes=none_if_empty(new_client_notes),
        )
        db.add(new_client)
        db.flush()
        log_action(
            db,
            user=user,
            action="create_client",
            entity_type="client",
            entity_id=new_client.id,
            new_value={"full_name": new_client.full_name},
            request=request,
        )
        resolved_client_id = new_client.id
    else:
        if not client_id:
            return templates.TemplateResponse(
                "agencies/form.html",
                _agency_context(db, request=request, user=user, agency=None, error="يجب اختيار عميل أو إدخال بيانات عميل جديد."),
                status_code=400,
            )
        resolved_client_id = int(client_id)

    parsed_matter_id = _validate_matter(db, resolved_client_id, matter_id)
    agency = Agency(
        agency_number=agency_number,
        title=title.strip(),
        client_id=resolved_client_id,
        matter_id=parsed_matter_id,
        issued_at=parse_date(issued_at),
        expires_at=parse_date(expires_at),
        status=status if status in AGENCY_STATUSES else "active",
        notary_office=none_if_empty(notary_office),
        authorized_person=none_if_empty(authorized_person),
        scope=none_if_empty(scope),
        notes=none_if_empty(notes),
    )
    db.add(agency)
    db.flush()
    log_action(
        db,
        user=user,
        action="create_agency",
        entity_type="agency",
        entity_id=agency.id,
        new_value={"agency_number": agency.agency_number, "title": agency.title, "client_id": agency.client_id},
        request=request,
    )
    db.commit()
    return RedirectResponse(f"/agencies/{agency.id}", status_code=303)


@router.get("/{agency_id}")
def agency_detail(
    request: Request,
    agency_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    agency = _get_agency(db, agency_id)
    return templates.TemplateResponse(
        "agencies/detail.html",
        {"request": request, "user": user, "agency": agency, "agency_statuses": AGENCY_STATUSES},
    )


@router.get("/{agency_id}/edit")
def agency_edit(
    request: Request,
    agency_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    agency = _get_agency(db, agency_id)
    return templates.TemplateResponse(
        "agencies/form.html",
        _agency_context(db, request=request, user=user, agency=agency),
    )


@router.post("/{agency_id}/edit")
def agency_update(
    request: Request,
    agency_id: int,
    agency_number: str = Form(...),
    title: str = Form(...),
    client_id: int = Form(...),
    matter_id: str = Form(""),
    issued_at: str = Form(""),
    expires_at: str = Form(""),
    status: str = Form("active"),
    notary_office: str = Form(""),
    authorized_person: str = Form(""),
    scope: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    agency = _get_agency(db, agency_id)
    agency_number = agency_number.strip()
    existing = db.scalar(select(Agency).where(Agency.agency_number == agency_number, Agency.id != agency_id))
    if existing:
        return templates.TemplateResponse(
            "agencies/form.html",
            _agency_context(db, request=request, user=user, agency=agency, error="رقم الوكالة مسجل مسبقاً."),
            status_code=400,
        )
    parsed_matter_id = _validate_matter(db, client_id, matter_id)
    old = {"agency_number": agency.agency_number, "title": agency.title, "status": agency.status}
    agency.agency_number = agency_number
    agency.title = title.strip()
    agency.client_id = client_id
    agency.matter_id = parsed_matter_id
    agency.issued_at = parse_date(issued_at)
    agency.expires_at = parse_date(expires_at)
    agency.status = status if status in AGENCY_STATUSES else "active"
    agency.notary_office = none_if_empty(notary_office)
    agency.authorized_person = none_if_empty(authorized_person)
    agency.scope = none_if_empty(scope)
    agency.notes = none_if_empty(notes)
    log_action(
        db,
        user=user,
        action="update_agency",
        entity_type="agency",
        entity_id=agency.id,
        old_value=old,
        new_value={"agency_number": agency.agency_number, "title": agency.title, "status": agency.status},
        request=request,
    )
    db.commit()
    return RedirectResponse(f"/agencies/{agency.id}", status_code=303)

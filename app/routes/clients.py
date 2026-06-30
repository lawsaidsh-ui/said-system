from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Client, Document, User
from app.routes.helpers import find_similar_client, none_if_empty, search_clients
from app.services.audit import audit_logs_for_targets, log_action
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("")
def clients_index(
    request: Request,
    q: str | None = None,
    client_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = search_clients(select(Client), q)
    if client_type:
        stmt = stmt.where(Client.client_type == client_type)
    clients = db.scalars(stmt.order_by(Client.created_at.desc())).all()
    return templates.TemplateResponse("clients/index.html", {"request": request, "user": user, "clients": clients, "q": q or "", "client_type": client_type or ""})


@router.get("/new")
def client_new(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"secretary", "lawyer", "data_entry"})
    return templates.TemplateResponse("clients/form.html", {"request": request, "user": user, "client": None})


@router.post("/new")
def client_create(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    civil_id: str = Form(""),
    address: str = Form(""),
    client_type: str = Form("individual"),
    company_name: str = Form(""),
    commercial_registration: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"secretary", "lawyer", "data_entry"})
    existing_client = find_similar_client(
        db,
        full_name,
        phone=none_if_empty(phone),
        civil_id=none_if_empty(civil_id),
        commercial_registration=none_if_empty(commercial_registration),
    )
    if existing_client:
        return RedirectResponse(f"/clients/{existing_client.id}", status_code=303)
    client = Client(
        full_name=full_name,
        phone=none_if_empty(phone),
        email=none_if_empty(email),
        civil_id=none_if_empty(civil_id),
        address=none_if_empty(address),
        client_type=client_type,
        company_name=none_if_empty(company_name),
        commercial_registration=none_if_empty(commercial_registration),
        notes=none_if_empty(notes),
    )
    db.add(client)
    db.flush()
    log_action(db, user=user, action="create_client", entity_type="client", entity_id=client.id, new_value={"full_name": client.full_name}, request=request)
    db.commit()
    return RedirectResponse(f"/clients/{client.id}", status_code=303)


@router.get("/{client_id}")
def client_detail(request: Request, client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    client = db.scalar(
        select(Client)
        .where(Client.id == client_id)
        .options(
            selectinload(Client.matters),
            selectinload(Client.documents).selectinload(Document.uploaded_by),
            selectinload(Client.invoices),
            selectinload(Client.consultations),
        )
    )
    audit_logs = []
    if user.role == "admin":
        matter_ids = [matter.id for matter in client.matters]
        document_ids = [document.id for document in client.documents]
        audit_logs = audit_logs_for_targets(
            db,
            [("client", client.id)]
            + [("matter", matter_id) for matter_id in matter_ids]
            + [("document", document_id) for document_id in document_ids],
        )
    return templates.TemplateResponse(
        "clients/detail.html",
        {"request": request, "user": user, "client": client, "audit_logs": audit_logs},
    )


@router.get("/{client_id}/edit")
def client_edit(request: Request, client_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"secretary", "lawyer", "data_entry"})
    return templates.TemplateResponse("clients/form.html", {"request": request, "user": user, "client": db.get(Client, client_id)})


@router.post("/{client_id}/edit")
def client_update(
    request: Request,
    client_id: int,
    full_name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    civil_id: str = Form(""),
    address: str = Form(""),
    client_type: str = Form("individual"),
    company_name: str = Form(""),
    commercial_registration: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"secretary", "lawyer", "data_entry"})
    client = db.get(Client, client_id)
    existing_client = find_similar_client(
        db,
        full_name,
        exclude_client_id=client_id,
        phone=none_if_empty(phone),
        civil_id=none_if_empty(civil_id),
        commercial_registration=none_if_empty(commercial_registration),
    )
    if existing_client:
        return templates.TemplateResponse(
            "clients/form.html",
            {
                "request": request,
                "user": user,
                "client": client,
                "error": f"يوجد عميل مشابه بالفعل: {existing_client.full_name}",
            },
            status_code=400,
        )
    old = {"full_name": client.full_name, "phone": client.phone}
    client.full_name = full_name
    client.phone = none_if_empty(phone)
    client.email = none_if_empty(email)
    client.civil_id = none_if_empty(civil_id)
    client.address = none_if_empty(address)
    client.client_type = client_type
    client.company_name = none_if_empty(company_name)
    client.commercial_registration = none_if_empty(commercial_registration)
    client.notes = none_if_empty(notes)
    log_action(db, user=user, action="update_client", entity_type="client", entity_id=client.id, old_value=old, new_value={"full_name": client.full_name}, request=request)
    db.commit()
    return RedirectResponse(f"/clients/{client.id}", status_code=303)

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Client, CourtDocumentTemplate, Document, GeneratedCourtDocument, Matter, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, setting_value
from app.services.audit import log_action
from app.services.auth import ensure_role, get_current_user, require_roles
from app.services.court_documents import (
    COURT_TEMPLATE_CATEGORIES,
    LETTER_VARIABLES,
    build_document_html,
    collect_auto_values,
    dumps,
    extract_variables,
    generate_pdf,
    loads_map,
    missing_variables,
    next_reference_number,
    sanitize_template_html,
    snapshot_asset,
)
from app.templating import templates

router = APIRouter(tags=["court_documents"])


def parse_roles(values: list[str] | None) -> list[str]:
    return [item for item in values or [] if item]


def can_use_template(user: User, template: CourtDocumentTemplate) -> bool:
    if user.role == "admin":
        return True
    roles = loads_map(template.allowed_roles).get("roles", [])
    return user.role in roles


def template_or_404(db: Session, template_id: int) -> CourtDocumentTemplate:
    item = db.get(CourtDocumentTemplate, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="النموذج غير موجود.")
    return item


def document_or_404(db: Session, document_id: int) -> GeneratedCourtDocument:
    item = db.scalar(
        select(GeneratedCourtDocument)
        .options(
            selectinload(GeneratedCourtDocument.template),
            selectinload(GeneratedCourtDocument.client),
            selectinload(GeneratedCourtDocument.matter),
            selectinload(GeneratedCourtDocument.issued_by),
        )
        .where(GeneratedCourtDocument.id == document_id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="الخطاب غير موجود.")
    return item


@router.get("/court-templates")
def court_templates_index(
    request: Request,
    q: str = "",
    category: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "data_entry", "viewer"})
    stmt = select(CourtDocumentTemplate).order_by(CourtDocumentTemplate.updated_at.desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(CourtDocumentTemplate.name.ilike(like), CourtDocumentTemplate.subject_template.ilike(like), CourtDocumentTemplate.target_entity.ilike(like)))
    if category:
        stmt = stmt.where(CourtDocumentTemplate.category == category)
    items = [item for item in db.scalars(stmt).all() if can_use_template(user, item)]
    return templates.TemplateResponse(
        "court_documents/templates_index.html",
        {"request": request, "user": user, "items": items, "categories": COURT_TEMPLATE_CATEGORIES, "q": q, "category": category},
    )


@router.get("/court-templates/new")
def court_template_new(request: Request, user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse(
        "court_documents/template_form.html",
        {"request": request, "user": user, "item": None, "categories": COURT_TEMPLATE_CATEGORIES, "variables": LETTER_VARIABLES},
    )


@router.post("/court-templates/new")
async def court_template_create(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    form = await request.form()
    body_html = sanitize_template_html(str(form.get("body_html") or ""))
    subject = str(form.get("subject_template") or "")
    variables = extract_variables(subject, body_html)
    item = CourtDocumentTemplate(
        name=str(form.get("name") or "").strip(),
        description=none_if_empty(str(form.get("description") or "")),
        category=str(form.get("category") or COURT_TEMPLATE_CATEGORIES[-1]),
        target_entity=none_if_empty(str(form.get("target_entity") or "")),
        subject_template=subject,
        body_html=body_html,
        variables_schema=dumps({"variables": variables}),
        allowed_roles=dumps({"roles": parse_roles(form.getlist("allowed_roles"))}),
        include_letterhead=bool(form.get("include_letterhead")),
        include_signature=bool(form.get("include_signature")),
        include_stamp=bool(form.get("include_stamp")),
        requires_approval=bool(form.get("requires_approval")),
        is_active=bool(form.get("is_active")),
        created_by_id=user.id,
    )
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_court_template", entity_type="court_document_template", entity_id=item.id, new_value={"name": item.name}, request=request)
    db.commit()
    return RedirectResponse("/court-templates", status_code=303)


@router.get("/court-templates/{template_id}/edit")
def court_template_edit(template_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse(
        "court_documents/template_form.html",
        {"request": request, "user": user, "item": template_or_404(db, template_id), "categories": COURT_TEMPLATE_CATEGORIES, "variables": LETTER_VARIABLES},
    )


@router.post("/court-templates/{template_id}/edit")
async def court_template_update(template_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = template_or_404(db, template_id)
    old = {"version": item.version, "name": item.name}
    form = await request.form()
    body_html = sanitize_template_html(str(form.get("body_html") or ""))
    item.name = str(form.get("name") or "").strip()
    item.description = none_if_empty(str(form.get("description") or ""))
    item.category = str(form.get("category") or COURT_TEMPLATE_CATEGORIES[-1])
    item.target_entity = none_if_empty(str(form.get("target_entity") or ""))
    item.subject_template = str(form.get("subject_template") or "")
    item.body_html = body_html
    item.variables_schema = dumps({"variables": extract_variables(item.subject_template, body_html)})
    item.allowed_roles = dumps({"roles": parse_roles(form.getlist("allowed_roles"))})
    item.include_letterhead = bool(form.get("include_letterhead"))
    item.include_signature = bool(form.get("include_signature"))
    item.include_stamp = bool(form.get("include_stamp"))
    item.requires_approval = bool(form.get("requires_approval"))
    item.is_active = bool(form.get("is_active"))
    item.version += 1
    log_action(db, user=user, action="update_court_template", entity_type="court_document_template", entity_id=item.id, old_value=old, new_value={"version": item.version}, request=request)
    db.commit()
    return RedirectResponse("/court-templates", status_code=303)


@router.post("/court-templates/{template_id}/delete")
def court_template_delete(template_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = template_or_404(db, template_id)
    item.is_active = False
    log_action(db, user=user, action="disable_court_template", entity_type="court_document_template", entity_id=item.id, request=request)
    db.commit()
    return RedirectResponse("/court-templates", status_code=303)


@router.get("/court-templates/{template_id}/preview", response_class=HTMLResponse)
def court_template_preview(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = template_or_404(db, template_id)
    values = collect_auto_values(db, client=None, matter=None, user=user, court_name=item.target_entity, department_name="", subject=item.subject_template)
    return build_document_html(
        db,
        template=item,
        subject=item.subject_template,
        body_html=item.body_html,
        values=values,
        user=user,
        reference_number=None,
        include_letterhead=item.include_letterhead,
        include_signature=False,
        include_stamp=False,
    )


@router.get("/court-templates/{template_id}/generate")
def court_template_generate(template_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = template_or_404(db, template_id)
    if not item.is_active or not can_use_template(user, item):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية استخدام هذا النموذج.")
    return templates.TemplateResponse(
        "court_documents/generate.html",
        {"request": request, "user": user, "item": item, "variables": LETTER_VARIABLES, **get_form_context(db)},
    )


@router.post("/court-templates/{template_id}/generate")
async def court_document_create(template_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    template = template_or_404(db, template_id)
    if not template.is_active or not can_use_template(user, template):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية استخدام هذا النموذج.")
    form = await request.form()
    client = db.get(Client, int_or_none(str(form.get("client_id") or ""))) if form.get("client_id") else None
    matter = db.get(Matter, int_or_none(str(form.get("matter_id") or ""))) if form.get("matter_id") else None
    if matter and not client:
        client = matter.client
    subject = str(form.get("subject") or template.subject_template)
    body_html = sanitize_template_html(str(form.get("body_html") or template.body_html))
    values = collect_auto_values(
        db,
        client=client,
        matter=matter,
        user=user,
        court_name=none_if_empty(str(form.get("court_name") or "")),
        department_name=none_if_empty(str(form.get("department_name") or "")),
        subject=subject,
    )
    for key, _label in LETTER_VARIABLES:
        manual = str(form.get(f"var_{key}") or "").strip()
        if manual:
            values[key] = manual
    status = "pending_approval" if form.get("action") == "submit_approval" or template.requires_approval else "draft"
    rendered = build_document_html(
        db,
        template=template,
        subject=subject,
        body_html=body_html,
        values=values,
        user=user,
        reference_number=None,
        include_letterhead=template.include_letterhead,
        include_signature=False,
        include_stamp=False,
    )
    document = GeneratedCourtDocument(
        template_id=template.id,
        template_version=template.version,
        client_id=client.id if client else None,
        matter_id=matter.id if matter else None,
        court_name=str(values.get("court_name") or ""),
        department_name=str(values.get("court_department") or ""),
        subject=subject,
        values_json=dumps(values),
        rendered_html_snapshot=rendered,
        template_snapshot=dumps({"subject_template": subject, "body_html": body_html, "template_name": template.name}),
        status=status,
        issued_by_id=user.id,
    )
    db.add(document)
    db.flush()
    action = "submit_court_document_approval" if status == "pending_approval" else "create_court_document_draft"
    log_action(db, user=user, action=action, entity_type="generated_court_document", entity_id=document.id, new_value={"status": status}, request=request)
    db.commit()
    return RedirectResponse(f"/court-documents/{document.id}/preview", status_code=303)


@router.get("/court-documents")
def court_documents_index(
    request: Request,
    q: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "data_entry", "viewer"})
    stmt = (
        select(GeneratedCourtDocument)
        .options(selectinload(GeneratedCourtDocument.client), selectinload(GeneratedCourtDocument.matter), selectinload(GeneratedCourtDocument.issued_by), selectinload(GeneratedCourtDocument.template))
        .order_by(GeneratedCourtDocument.created_at.desc())
    )
    if user.role not in {"admin", "lawyer"}:
        stmt = stmt.where(GeneratedCourtDocument.issued_by_id == user.id)
    if status:
        stmt = stmt.where(GeneratedCourtDocument.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(GeneratedCourtDocument.reference_number.ilike(like), GeneratedCourtDocument.subject.ilike(like), GeneratedCourtDocument.court_name.ilike(like)))
    documents = db.scalars(stmt).all()
    return templates.TemplateResponse("court_documents/documents_index.html", {"request": request, "user": user, "documents": documents, "q": q, "status": status})


@router.get("/court-documents/{document_id}/preview", response_class=HTMLResponse)
def court_document_preview(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = document_or_404(db, document_id)
    if user.role not in {"admin", "lawyer"} and document.issued_by_id != user.id:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية عرض هذا الخطاب.")
    return document.rendered_html_snapshot or ""


@router.post("/court-documents/{document_id}/issue")
def court_document_issue(document_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = document_or_404(db, document_id)
    template = document.template
    if not template:
        raise HTTPException(status_code=400, detail="النموذج الأصلي غير متوفر.")
    if document.status == "issued":
        return RedirectResponse("/court-documents", status_code=303)
    if user.role == "secretary" and not user.can_issue_signed_letters:
        raise HTTPException(status_code=403, detail="لا يملك السكرتير صلاحية اعتماد الخطابات.")
    if template.include_signature and (not user.can_issue_signed_letters or not user.signature_path):
        raise HTTPException(status_code=400, detail="لا يمكن الإصدار لأن النموذج يتطلب توقيعًا محفوظًا وصلاحية إصدار.")
    if template.include_stamp and not user.can_use_office_stamp:
        raise HTTPException(status_code=403, detail="لا تملك صلاحية استخدام ختم المكتب.")
    values = loads_map(document.values_json)
    values["reference_number"] = next_reference_number(db)
    missing = missing_variables(template, values)
    if missing:
        raise HTTPException(status_code=400, detail=f"توجد متغيرات غير مكتملة: {', '.join(missing)}")
    snapshot = loads_map(document.template_snapshot)
    rendered = build_document_html(
        db,
        template=template,
        subject=document.subject,
        body_html=snapshot.get("body_html", template.body_html),
        values=values,
        user=user,
        reference_number=values["reference_number"],
        include_letterhead=template.include_letterhead,
        include_signature=template.include_signature,
        include_stamp=template.include_stamp,
    )
    pdf_url, pdf_name, pdf_size = generate_pdf(rendered, values["reference_number"])
    document.reference_number = values["reference_number"]
    document.values_json = dumps(values)
    document.rendered_html_snapshot = rendered
    document.signature_snapshot_path = snapshot_asset(user.signature_path, "court-document-assets")
    document.letterhead_snapshot_path = snapshot_asset(setting_value(db, "court_letterhead_path"), "court-document-assets")
    document.stamp_snapshot_path = snapshot_asset(setting_value(db, "court_stamp_path"), "court-document-assets")
    document.pdf_path = pdf_url
    document.status = "issued"
    document.issued_by_id = user.id
    document.issued_at = datetime.utcnow()
    document.approved_by_id = user.id
    document.approved_at = datetime.utcnow()
    db.add(
        Document(
            matter_id=document.matter_id,
            client_id=document.client_id,
            uploaded_by_id=user.id,
            document_type="court_letter",
            title=document.subject,
            file_url=pdf_url,
            file_name=pdf_name,
            file_size=pdf_size,
            mime_type="application/pdf",
            notes=f"خطاب قضائي صادر برقم {document.reference_number}",
            is_confidential=True,
        )
    )
    log_action(db, user=user, action="issue_court_document_pdf", entity_type="generated_court_document", entity_id=document.id, new_value={"reference_number": document.reference_number}, request=request)
    db.commit()
    return RedirectResponse("/court-documents", status_code=303)


@router.get("/court-documents/{document_id}/download")
def court_document_download(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = document_or_404(db, document_id)
    if not document.pdf_path:
        raise HTTPException(status_code=404, detail="ملف PDF غير متوفر.")
    path = "app/static" + document.pdf_path.removeprefix("/static")
    return FileResponse(path, media_type="application/pdf", filename=(document.reference_number or "court-document").replace("/", "-") + ".pdf")


@router.post("/court-documents/{document_id}/revoke")
def court_document_revoke(document_id: int, request: Request, reason: str = Form(...), db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    document = document_or_404(db, document_id)
    if document.status != "issued":
        raise HTTPException(status_code=400, detail="يمكن إلغاء الخطابات المعتمدة فقط.")
    document.status = "revoked"
    document.revoked_by_id = user.id
    document.revoked_at = datetime.utcnow()
    document.revocation_reason = reason
    log_action(db, user=user, action="revoke_court_document", entity_type="generated_court_document", entity_id=document.id, new_value={"reason": reason}, request=request)
    db.commit()
    return RedirectResponse("/court-documents", status_code=303)

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, WhatsAppLog, WhatsAppTemplate
from app.services.auth import get_current_user, require_roles
from app.services.whatsapp import (
    WHATSAPP_TEMPLATE_TYPES,
    WHATSAPP_VARIABLES,
    ensure_default_templates,
    normalize_phone,
    source_context,
    template_options,
    whatsapp_url,
)
from app.templating import templates

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/compose")
def compose_message(
    source_type: str,
    source_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        context = source_context(db, source_type, source_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="تعذر العثور على البيانات المطلوبة.")
    phone_clean, phone_error = normalize_phone(context["phone_raw"])
    options = template_options(db, context["variables"], context.get("template_variables"))
    return JSONResponse(
        {
            "source_type": source_type,
            "source_id": source_id,
            "client_id": context["client"].id if context["client"] else None,
            "matter_id": context["matter"].id if context["matter"] else None,
            "client_name": context["variables"]["client_name"],
            "phone_raw": context["phone_raw"],
            "phone_clean": phone_clean,
            "phone_error": phone_error,
            "templates": options,
            "variables": context["variables"],
        }
    )


@router.post("/log")
def log_message_attempt(
    source_type: str = Form(...),
    source_id: int = Form(...),
    template_id: str = Form(""),
    message: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if status not in {"opened", "cancelled"}:
        raise HTTPException(status_code=400, detail="حالة غير صحيحة.")
    try:
        context = source_context(db, source_type, source_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="تعذر العثور على البيانات المطلوبة.")

    selected_template = db.get(WhatsAppTemplate, int(template_id)) if template_id else None
    phone_clean, phone_error = normalize_phone(context["phone_raw"])
    if status == "opened" and phone_error:
        raise HTTPException(status_code=400, detail=phone_error)

    log = WhatsAppLog(
        client_id=context["client"].id if context["client"] else None,
        matter_id=context["matter"].id if context["matter"] else None,
        template_id=selected_template.id if selected_template else None,
        template_type=selected_template.template_type if selected_template else None,
        message=message,
        phone_raw=context["phone_raw"],
        phone_clean=phone_clean,
        employee_id=user.id,
        source_type=source_type,
        source_id=source_id,
        status="تم فتح واتساب" if status == "opened" else "تم الإلغاء",
    )
    db.add(log)
    db.commit()
    return JSONResponse(
        {
            "ok": True,
            "url": whatsapp_url(phone_clean, message) if status == "opened" and phone_clean else None,
        }
    )


@router.get("/templates")
def templates_index(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    ensure_default_templates(db)
    items = db.scalars(select(WhatsAppTemplate).order_by(WhatsAppTemplate.id)).all()
    return templates.TemplateResponse(
        "whatsapp/templates.html",
        {
            "request": request,
            "user": user,
            "templates": items,
            "template_types": WHATSAPP_TEMPLATE_TYPES,
            "variables": WHATSAPP_VARIABLES,
        },
    )


@router.post("/templates")
def template_create(
    name: str = Form(...),
    template_type: str = Form(...),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    db.add(WhatsAppTemplate(name=name, template_type=template_type, body=body, is_active=True))
    db.commit()
    return RedirectResponse("/whatsapp/templates", status_code=303)


@router.post("/templates/{template_id}/update")
def template_update(
    template_id: int,
    name: str = Form(...),
    template_type: str = Form(...),
    body: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    item = db.get(WhatsAppTemplate, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="القالب غير موجود.")
    item.name = name
    item.template_type = template_type
    item.body = body
    db.commit()
    return RedirectResponse("/whatsapp/templates", status_code=303)


@router.post("/templates/{template_id}/toggle")
def template_toggle(template_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = db.get(WhatsAppTemplate, template_id)
    if not item:
        raise HTTPException(status_code=404, detail="القالب غير موجود.")
    item.is_active = not item.is_active
    db.commit()
    return RedirectResponse("/whatsapp/templates", status_code=303)

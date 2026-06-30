import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.audit import log_action
from app.services.auth import require_roles
from app.services.security import hash_password
from app.templating import templates

router = APIRouter(prefix="/users", tags=["users"])
PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_temporary_password(length: int = 14) -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))


@router.get("")
def users_index(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse("users/index.html", {"request": request, "user": user, "users": db.scalars(select(User).order_by(User.created_at.desc())).all(), "reset_result": None})


@router.get("/new")
def user_new(request: Request, user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "item": None})


@router.post("/new")
def user_create(request: Request, full_name: str = Form(...), email: str = Form(...), phone: str = Form(""), password: str = Form(...), role: str = Form("viewer"), is_active: str | None = Form(None), db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = User(full_name=full_name, email=email, phone=phone or None, password_hash=hash_password(password), role=role, is_active=bool(is_active))
    db.add(item)
    db.flush()
    log_action(db, user=user, action="create_user", entity_type="user", entity_id=item.id, new_value={"email": email, "role": role}, request=request)
    db.commit()
    return RedirectResponse("/users", status_code=303)


@router.get("/{user_id}/edit")
def user_edit(request: Request, user_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return templates.TemplateResponse("users/form.html", {"request": request, "user": user, "item": db.get(User, user_id)})


@router.post("/{user_id}/edit")
def user_update(request: Request, user_id: int, full_name: str = Form(...), email: str = Form(...), phone: str = Form(""), password: str = Form(""), role: str = Form("viewer"), is_active: str | None = Form(None), db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = db.get(User, user_id)
    old = {"role": item.role, "is_active": item.is_active}
    item.full_name = full_name
    item.email = email
    item.phone = phone or None
    item.role = role
    item.is_active = bool(is_active)
    if password:
        item.password_hash = hash_password(password)
    log_action(db, user=user, action="change_user_role", entity_type="user", entity_id=item.id, old_value=old, new_value={"role": role, "is_active": item.is_active}, request=request)
    db.commit()
    return RedirectResponse("/users", status_code=303)


@router.post("/{user_id}/reset-password")
def user_reset_password(request: Request, user_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    item = db.get(User, user_id)
    if not item:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود.")
    temporary_password = generate_temporary_password()
    item.password_hash = hash_password(temporary_password)
    log_action(
        db,
        user=user,
        action="reset_user_password",
        entity_type="user",
        entity_id=item.id,
        new_value={"email": item.email},
        request=request,
    )
    db.commit()
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return templates.TemplateResponse(
        "users/index.html",
        {
            "request": request,
            "user": user,
            "users": users,
            "reset_result": {
                "full_name": item.full_name,
                "email": item.email,
                "password": temporary_password,
            },
        },
    )

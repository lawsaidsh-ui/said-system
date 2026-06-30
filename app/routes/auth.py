from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.security import verify_password
from app.templating import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "بيانات الدخول غير صحيحة أو الحساب غير نشط."},
            status_code=400,
        )
    user.last_login_at = datetime.utcnow()
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/forgot-password")
def forgot_password(request: Request):
    return templates.TemplateResponse("auth/forgot_password.html", {"request": request})

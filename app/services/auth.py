from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


WRITE_ROLES = {"admin", "lawyer", "secretary", "accountant", "data_entry"}
CONFIDENTIAL_ROLES = {"admin", "lawyer"}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليست لديك صلاحية كافية")
        return user

    return dependency


def ensure_role(user: User, roles: set[str] | tuple[str, ...] | list[str]) -> None:
    if user.role == "admin":
        return
    if user.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليست لديك صلاحية كافية")


def ensure_not_viewer(user: User) -> None:
    if user.role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="المستخدم بصلاحية مشاهدة فقط")

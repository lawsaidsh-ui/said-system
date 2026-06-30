from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OfficeSetting, User
from app.services.auth import require_roles
from app.services.tasks import TASK_SETTING_DEFAULTS, ensure_task_settings
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def settings_index(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    ensure_task_settings(db)
    keys = [
        ("office_name", "اسم المكتب"),
        ("logo", "الشعار"),
        ("phone", "رقم الهاتف"),
        ("email", "البريد"),
        ("address", "العنوان"),
        ("invoice_footer", "نصوص الفواتير"),
    ]
    task_rule_keys = [
        ("task_collection_reminder_days", "تذكير التحصيل قبل الاستحقاق بعدد أيام", "number"),
        ("task_session_reminder_days", "تذكيرات الجلسات قبل الموعد بالأيام، مفصولة بفواصل", "text"),
        ("task_default_accountant_id", "المحاسب الافتراضي لمهام التحصيل", "user"),
        ("task_default_secretary_id", "الموظف الافتراضي لمتابعة العملاء", "user"),
        ("task_default_lawyer_id", "المحامي الافتراضي إذا لم تكن القضية مسندة", "user"),
        ("task_enable_weekly_tasks", "إنشاء مهام أسبوعية تلقائياً", "bool"),
        ("task_enable_monthly_tasks", "إنشاء مهام شهرية تلقائياً", "bool"),
        ("task_notify_manager_overdue", "إشعار المدير عند تراكم التأخير", "bool"),
        ("task_overdue_manager_threshold", "حد المهام المتأخرة قبل إشعار المدير", "number"),
    ]
    settings_map = {item.key: item for item in db.scalars(select(OfficeSetting)).all()}
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    return templates.TemplateResponse(
        "settings/index.html",
        {
            "request": request,
            "user": user,
            "keys": keys,
            "task_rule_keys": task_rule_keys,
            "settings_map": settings_map,
            "task_setting_defaults": TASK_SETTING_DEFAULTS,
            "users": users,
        },
    )


@router.post("")
async def settings_update(request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    form = await request.form()
    for key, value in form.items():
        item = db.scalar(select(OfficeSetting).where(OfficeSetting.key == key))
        if item:
            item.value = str(value)
        else:
            db.add(OfficeSetting(key=key, value=str(value), description=key))
    db.commit()
    return RedirectResponse("/settings", status_code=303)

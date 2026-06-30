from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import CourtSession, Invoice, Matter, Notification, OfficeSetting, Task, User


OPEN_TASK_STATUSES = {"new", "pending", "in_progress"}
OPEN_MATTER_STATUSES = {"new", "open", "in_progress", "waiting", "court_session"}
UNPAID_INVOICE_STATUSES = {"unpaid", "partially_paid"}

TASK_SETTING_DEFAULTS = {
    "task_collection_reminder_days": "3",
    "task_session_reminder_days": "7,3,1",
    "task_default_accountant_id": "",
    "task_default_secretary_id": "",
    "task_default_lawyer_id": "",
    "task_enable_weekly_tasks": "1",
    "task_enable_monthly_tasks": "1",
    "task_notify_manager_overdue": "1",
    "task_overdue_manager_threshold": "5",
}


def task_setting(db: Session, key: str) -> str:
    setting = db.scalar(select(OfficeSetting).where(OfficeSetting.key == key))
    return setting.value if setting and setting.value is not None else TASK_SETTING_DEFAULTS.get(key, "")


def task_setting_bool(db: Session, key: str) -> bool:
    return task_setting(db, key).strip().lower() in {"1", "true", "yes", "on", "نعم"}


def task_setting_int(db: Session, key: str, default: int) -> int:
    try:
        return int(task_setting(db, key))
    except (TypeError, ValueError):
        return default


def task_setting_days(db: Session, key: str, default: list[int]) -> list[int]:
    raw = task_setting(db, key)
    days: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            days.append(int(item))
    return days or default


def ensure_task_settings(db: Session) -> None:
    for key, value in TASK_SETTING_DEFAULTS.items():
        if not db.scalar(select(OfficeSetting.id).where(OfficeSetting.key == key)):
            db.add(OfficeSetting(key=key, value=value, description="إعداد قاعدة مهام تلقائية"))
    db.commit()


def preferred_user_for_role(db: Session, role: str, setting_key: str | None = None) -> User | None:
    if setting_key:
        raw_id = task_setting(db, setting_key)
        if raw_id.isdigit():
            user = db.get(User, int(raw_id))
            if user and user.is_active:
                return user
    roles = [role]
    if role == "manager":
        roles = ["admin"]
    elif role == "secretary":
        roles = ["secretary", "data_entry"]
    user = db.scalar(select(User).where(User.role.in_(roles), User.is_active.is_(True)).order_by(User.id))
    if user:
        return user
    return db.scalar(select(User).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id))


def task_exists(db: Session, source_key: str) -> bool:
    return bool(db.scalar(select(Task.id).where(Task.source_key == source_key)))


def notification_exists(db: Session, source_key: str) -> bool:
    return bool(db.scalar(select(Notification.id).where(Notification.source_key == source_key)))


def create_notification(
    db: Session,
    *,
    user_id: int | None,
    task: Task | None,
    title: str,
    message: str,
    notification_type: str,
    source_key: str,
) -> Notification | None:
    if notification_exists(db, source_key):
        return None
    notification = Notification(
        user_id=user_id,
        task_id=task.id if task else None,
        title=title,
        message=message,
        notification_type=notification_type,
        channel="in_app",
        status="new",
        source_key=source_key,
    )
    db.add(notification)
    return notification


def create_task_once(
    db: Session,
    *,
    source_key: str,
    title: str,
    task_type: str,
    assigned_role: str,
    assigned_to_id: int | None,
    due_date: date | None,
    priority: str = "medium",
    description: str | None = None,
    matter_id: int | None = None,
    client_id: int | None = None,
    invoice_id: int | None = None,
    notes: str | None = None,
) -> Task | None:
    if task_exists(db, source_key):
        return None
    task = Task(
        title=title,
        description=description,
        task_type=task_type,
        assigned_role=assigned_role,
        assigned_to_id=assigned_to_id,
        due_date=due_date,
        priority=priority,
        status="new",
        source="auto",
        source_key=source_key,
        matter_id=matter_id,
        client_id=client_id,
        invoice_id=invoice_id,
        notes=notes,
    )
    db.add(task)
    db.flush()
    create_notification(
        db,
        user_id=assigned_to_id,
        task=task,
        title="مهمة جديدة",
        message=title,
        notification_type="task_created",
        source_key=f"task_created:{source_key}",
    )
    return task


def mark_overdue_tasks(db: Session, today: date) -> None:
    tasks = db.scalars(select(Task).where(Task.due_date < today, Task.status.in_(OPEN_TASK_STATUSES))).all()
    for task in tasks:
        task.status = "overdue"
        create_notification(
            db,
            user_id=task.assigned_to_id,
            task=task,
            title="مهمة متأخرة",
            message=f"تأخرت المهمة: {task.title}",
            notification_type="task_overdue",
            source_key=f"task_overdue:{task.id}:{today.isoformat()}",
        )


def notify_due_soon(db: Session, today: date) -> None:
    soon = today + timedelta(days=1)
    tasks = db.scalars(
        select(Task).where(Task.due_date.between(today, soon), Task.status.in_(OPEN_TASK_STATUSES | {"overdue"}))
    ).all()
    for task in tasks:
        create_notification(
            db,
            user_id=task.assigned_to_id,
            task=task,
            title="موعد مهمة قريب",
            message=f"المهمة تستحق في {task.due_date}: {task.title}",
            notification_type="task_due_soon",
            source_key=f"task_due_soon:{task.id}:{today.isoformat()}",
        )


def generate_finance_tasks(db: Session, today: date) -> None:
    accountant = preferred_user_for_role(db, "accountant", "task_default_accountant_id")
    accountant_id = accountant.id if accountant else None
    reminder_days = task_setting_int(db, "task_collection_reminder_days", 3)
    invoices = db.scalars(
        select(Invoice)
        .options(selectinload(Invoice.client), selectinload(Invoice.matter))
        .where(Invoice.status.in_(UNPAID_INVOICE_STATUSES))
    ).all()
    for invoice in invoices:
        remaining = invoice.total_amount - invoice.paid_amount
        due = invoice.due_date or today
        create_task_once(
            db,
            source_key=f"invoice_collection:{invoice.id}",
            title=f"تحصيل فاتورة {invoice.invoice_number}",
            description=f"المتبقي على العميل {invoice.client.full_name if invoice.client else ''}: {remaining}",
            task_type="collection",
            assigned_role="accountant",
            assigned_to_id=accountant_id,
            due_date=due,
            priority="high",
            matter_id=invoice.matter_id,
            client_id=invoice.client_id,
            invoice_id=invoice.id,
        )
        if invoice.due_date and today >= invoice.due_date - timedelta(days=reminder_days):
            create_task_once(
                db,
                source_key=f"invoice_due_before:{invoice.id}:{reminder_days}",
                title=f"تذكير تحصيل قبل الاستحقاق: {invoice.invoice_number}",
                task_type="invoice_followup",
                assigned_role="accountant",
                assigned_to_id=accountant_id,
                due_date=invoice.due_date - timedelta(days=reminder_days),
                priority="medium",
                matter_id=invoice.matter_id,
                client_id=invoice.client_id,
                invoice_id=invoice.id,
            )
        if invoice.due_date and today >= invoice.due_date:
            create_task_once(
                db,
                source_key=f"invoice_due_today:{invoice.id}",
                title=f"متابعة فاتورة مستحقة اليوم: {invoice.invoice_number}",
                task_type="invoice_followup",
                assigned_role="accountant",
                assigned_to_id=accountant_id,
                due_date=invoice.due_date,
                priority="high",
                matter_id=invoice.matter_id,
                client_id=invoice.client_id,
                invoice_id=invoice.id,
            )
        if invoice.due_date and today > invoice.due_date:
            create_task_once(
                db,
                source_key=f"invoice_overdue_followup:{invoice.id}",
                title=f"متابعة فاتورة متأخرة: {invoice.invoice_number}",
                description="لم يتم السداد بعد تاريخ الاستحقاق.",
                task_type="collection",
                assigned_role="accountant",
                assigned_to_id=accountant_id,
                due_date=today,
                priority="urgent",
                matter_id=invoice.matter_id,
                client_id=invoice.client_id,
                invoice_id=invoice.id,
            )

    if task_setting_bool(db, "task_enable_weekly_tasks"):
        year, week, _ = today.isocalendar()
        create_task_once(
            db,
            source_key=f"weekly_due_payments:{year}:{week}",
            title="مراجعة أسبوعية للمدفوعات المستحقة",
            task_type="collection",
            assigned_role="accountant",
            assigned_to_id=accountant_id,
            due_date=today,
            priority="medium",
        )
    if task_setting_bool(db, "task_enable_monthly_tasks"):
        create_task_once(
            db,
            source_key=f"monthly_revenue_expense_review:{today:%Y-%m}",
            title="مراجعة شهرية للإيرادات والمصروفات",
            task_type="internal_reminder",
            assigned_role="accountant",
            assigned_to_id=accountant_id,
            due_date=today,
            priority="high",
        )


def generate_matter_tasks(db: Session, today: date) -> None:
    secretary = preferred_user_for_role(db, "secretary", "task_default_secretary_id")
    default_lawyer = preferred_user_for_role(db, "lawyer", "task_default_lawyer_id")
    matters = db.scalars(
        select(Matter)
        .options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer), selectinload(Matter.documents), selectinload(Matter.sessions))
        .where(Matter.status.in_(OPEN_MATTER_STATUSES))
    ).all()
    now = datetime.now()
    for matter in matters:
        opened = matter.opened_at or (matter.created_at.date() if matter.created_at else today)
        lawyer_id = matter.assigned_lawyer_id or (default_lawyer.id if default_lawyer else None)
        secretary_id = secretary.id if secretary else None
        create_task_once(
            db,
            source_key=f"matter_client_followup:{matter.id}",
            title=f"متابعة العميل بعد فتح المعاملة: {matter.case_number}",
            task_type="client_followup",
            assigned_role="secretary",
            assigned_to_id=secretary_id,
            due_date=opened + timedelta(days=1),
            priority="medium",
            matter_id=matter.id,
            client_id=matter.client_id,
        )
        if not matter.documents:
            create_task_once(
                db,
                source_key=f"matter_missing_documents:{matter.id}",
                title=f"طلب المستندات الناقصة: {matter.case_number}",
                task_type="document_preparation",
                assigned_role="secretary",
                assigned_to_id=secretary_id,
                due_date=today,
                priority="high",
                matter_id=matter.id,
                client_id=matter.client_id,
            )
        if matter.updated_at and matter.updated_at < now - timedelta(hours=48):
            create_task_once(
                db,
                source_key=f"matter_no_update_48h:{matter.id}:{today.isoformat()}",
                title=f"الرد على العميل لعدم تحديث المعاملة خلال 48 ساعة: {matter.case_number}",
                task_type="client_followup",
                assigned_role="secretary",
                assigned_to_id=secretary_id,
                due_date=today,
                priority="medium",
                matter_id=matter.id,
                client_id=matter.client_id,
            )
        create_task_once(
            db,
            source_key=f"matter_file_review:{matter.id}",
            title=f"مراجعة ملف القضية: {matter.case_number}",
            task_type="document_preparation",
            assigned_role="lawyer",
            assigned_to_id=lawyer_id,
            due_date=opened + timedelta(days=1),
            priority=matter.priority if matter.priority in {"high", "urgent"} else "medium",
            matter_id=matter.id,
            client_id=matter.client_id,
        )
        if "تنفيذ" in " ".join(filter(None, [matter.case_type, matter.court_level, matter.status, matter.title])):
            create_task_once(
                db,
                source_key=f"matter_execution_review:{matter.id}",
                title=f"مراجعة إجراءات التنفيذ: {matter.case_number}",
                task_type="execution_followup",
                assigned_role="lawyer",
                assigned_to_id=lawyer_id,
                due_date=today,
                priority="high",
                matter_id=matter.id,
                client_id=matter.client_id,
            )


def generate_filing_deadline_tasks(db: Session, today: date) -> None:
    default_lawyer = preferred_user_for_role(db, "lawyer", "task_default_lawyer_id")
    matters = db.scalars(
        select(Matter)
        .options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
        .where(
            Matter.status != "archived",
            or_(Matter.appeal_deadline.is_not(None), Matter.cassation_deadline.is_not(None)),
        )
    ).all()
    for matter in matters:
        lawyer_id = matter.assigned_lawyer_id or (default_lawyer.id if default_lawyer else None)
        deadlines = [
            ("appeal", "الاستئناف", matter.appeal_deadline),
            ("cassation", "الطعن", matter.cassation_deadline),
        ]
        for deadline_key, deadline_label, deadline in deadlines:
            if not deadline:
                continue
            days_remaining = (deadline - today).days
            if days_remaining < 0:
                create_task_once(
                    db,
                    source_key=f"filing_deadline_overdue:{matter.id}:{deadline_key}",
                    title=f"انتهت مدة رفع صحيفة {deadline_label}: {matter.case_number}",
                    description=f"آخر موعد كان {deadline}. راجع الإجراء القانوني المناسب فوراً.",
                    task_type="judgment_followup",
                    assigned_role="lawyer",
                    assigned_to_id=lawyer_id,
                    due_date=today,
                    priority="urgent",
                    matter_id=matter.id,
                    client_id=matter.client_id,
                )
                continue
            priority = "urgent" if days_remaining <= 1 else "high" if days_remaining <= 3 else "medium"
            create_task_once(
                db,
                source_key=f"daily_filing_deadline:{matter.id}:{deadline_key}:{today.isoformat()}",
                title=f"تذكير يومي بمدة رفع صحيفة {deadline_label}: {matter.case_number}",
                description=f"متبقٍ {days_remaining} يوم. آخر موعد: {deadline}.",
                task_type="judgment_followup",
                assigned_role="lawyer",
                assigned_to_id=lawyer_id,
                due_date=today,
                priority=priority,
                matter_id=matter.id,
                client_id=matter.client_id,
            )


def generate_session_tasks(db: Session, today: date) -> None:
    default_lawyer = preferred_user_for_role(db, "lawyer", "task_default_lawyer_id")
    reminder_days = task_setting_days(db, "task_session_reminder_days", [7, 3, 1])
    sessions = db.scalars(
        select(CourtSession)
        .options(selectinload(CourtSession.matter).selectinload(Matter.client), selectinload(CourtSession.matter).selectinload(Matter.assigned_lawyer))
        .where(CourtSession.session_status.in_(["scheduled", "completed"]))
    ).all()
    for session in sessions:
        matter = session.matter
        if not matter:
            continue
        lawyer_id = matter.assigned_lawyer_id or (default_lawyer.id if default_lawyer else None)
        if session.session_status == "scheduled" and session.session_date >= today:
            for days in reminder_days:
                reminder_due = session.session_date - timedelta(days=days)
                if today >= reminder_due:
                    create_task_once(
                        db,
                        source_key=f"session_reminder:{session.id}:{days}",
                        title=f"تذكير جلسة بعد {days} يوم: {matter.case_number}",
                        task_type="session_followup",
                        assigned_role="lawyer",
                        assigned_to_id=lawyer_id,
                        due_date=reminder_due,
                        priority="high" if days <= 3 else "medium",
                        matter_id=matter.id,
                        client_id=matter.client_id,
                    )
            prepare_due = session.session_date - timedelta(days=3)
            if today >= prepare_due:
                create_task_once(
                    db,
                    source_key=f"session_document_prepare:{session.id}",
                    title=f"تجهيز مذكرة أو مستند قبل الجلسة: {matter.case_number}",
                    task_type="document_preparation",
                    assigned_role="lawyer",
                    assigned_to_id=lawyer_id,
                    due_date=prepare_due,
                    priority="high",
                    matter_id=matter.id,
                    client_id=matter.client_id,
                )
        if session.session_status == "completed" and session.decision_summary:
            create_task_once(
                db,
                source_key=f"judgment_followup:{session.id}",
                title=f"متابعة الحكم أو القرار: {matter.case_number}",
                task_type="judgment_followup",
                assigned_role="lawyer",
                assigned_to_id=lawyer_id,
                due_date=today,
                priority="high",
                matter_id=matter.id,
                client_id=matter.client_id,
                description=session.decision_summary,
            )


def generate_manager_tasks(db: Session, today: date) -> None:
    manager = preferred_user_for_role(db, "manager")
    manager_id = manager.id if manager else None
    if task_setting_bool(db, "task_enable_weekly_tasks"):
        year, week, _ = today.isocalendar()
        create_task_once(
            db,
            source_key=f"weekly_staff_performance:{year}:{week}",
            title="مراجعة أسبوعية لأداء الموظفين",
            task_type="internal_reminder",
            assigned_role="admin",
            assigned_to_id=manager_id,
            due_date=today,
            priority="medium",
        )
    if task_setting_bool(db, "task_enable_monthly_tasks"):
        create_task_once(
            db,
            source_key=f"monthly_collection_revenue_review:{today:%Y-%m}",
            title="مراجعة شهرية للتحصيل والإيرادات",
            task_type="collection",
            assigned_role="admin",
            assigned_to_id=manager_id,
            due_date=today,
            priority="high",
        )
    stale_cutoff = datetime.now() - timedelta(days=14)
    matters = db.scalars(select(Matter).where(Matter.status.in_(OPEN_MATTER_STATUSES), Matter.updated_at < stale_cutoff)).all()
    for matter in matters:
        create_task_once(
            db,
            source_key=f"manager_stale_matter:{matter.id}:{today:%Y-%m-%d}",
            title=f"متابعة قضية متأخرة: {matter.case_number}",
            task_type="internal_reminder",
            assigned_role="admin",
            assigned_to_id=manager_id,
            due_date=today,
            priority="urgent",
            matter_id=matter.id,
            client_id=matter.client_id,
        )

    if task_setting_bool(db, "task_notify_manager_overdue"):
        threshold = task_setting_int(db, "task_overdue_manager_threshold", 5)
        rows = db.execute(
            select(Task.assigned_to_id, func.count(Task.id))
            .where(Task.status == "overdue", Task.assigned_to_id.is_not(None))
            .group_by(Task.assigned_to_id)
        ).all()
        for assigned_to_id, count in rows:
            if count >= threshold:
                employee = db.get(User, assigned_to_id)
                create_notification(
                    db,
                    user_id=manager_id,
                    task=None,
                    title="تراكم مهام متأخرة",
                    message=f"لدى {employee.full_name if employee else 'موظف'} {count} مهام متأخرة.",
                    notification_type="manager_overdue_alert",
                    source_key=f"manager_overdue_alert:{assigned_to_id}:{today.isoformat()}",
                )

    urgent_count = db.scalar(select(func.count(Task.id)).where(Task.priority == "urgent", Task.status.in_(OPEN_TASK_STATUSES | {"overdue"}))) or 0
    overdue_count = db.scalar(select(func.count(Task.id)).where(Task.status == "overdue")) or 0
    create_notification(
        db,
        user_id=manager_id,
        task=None,
        title="تقرير المهام اليومي",
        message=f"المهام العاجلة المفتوحة: {urgent_count}، المهام المتأخرة: {overdue_count}.",
        notification_type="daily_task_report",
        source_key=f"daily_task_report:{today.isoformat()}",
    )


def generate_automatic_tasks(db: Session, today: date | None = None) -> None:
    today = today or date.today()
    ensure_task_settings(db)
    mark_overdue_tasks(db, today)
    generate_finance_tasks(db, today)
    generate_matter_tasks(db, today)
    generate_filing_deadline_tasks(db, today)
    generate_session_tasks(db, today)
    generate_manager_tasks(db, today)
    notify_due_soon(db, today)
    db.commit()


def create_matter_status_change_task(db: Session, *, matter: Matter, old_status: str, new_status: str) -> None:
    if old_status == new_status:
        return
    secretary = preferred_user_for_role(db, "secretary", "task_default_secretary_id")
    create_task_once(
        db,
        source_key=f"matter_status_update:{matter.id}:{new_status}:{date.today().isoformat()}",
        title=f"إرسال تحديث للعميل عن حالة المعاملة: {matter.case_number}",
        description=f"تغيرت الحالة من {old_status} إلى {new_status}.",
        task_type="client_followup",
        assigned_role="secretary",
        assigned_to_id=secretary.id if secretary else None,
        due_date=date.today(),
        priority="medium",
        matter_id=matter.id,
        client_id=matter.client_id,
    )


def scoped_task_statement(user: User):
    stmt = select(Task).options(
        selectinload(Task.assigned_to),
        selectinload(Task.client),
        selectinload(Task.matter).selectinload(Matter.assigned_lawyer),
        selectinload(Task.invoice),
    )
    if user.role == "admin":
        return stmt
    if user.role == "accountant":
        return stmt.where(
            or_(
                Task.assigned_to_id == user.id,
                Task.assigned_role == "accountant",
                Task.task_type.in_(["collection", "invoice_followup"]),
            )
        )
    if user.role == "lawyer":
        return stmt.where(or_(Task.assigned_to_id == user.id, Task.matter.has(Matter.assigned_lawyer_id == user.id)))
    return stmt.where(Task.assigned_to_id == user.id)

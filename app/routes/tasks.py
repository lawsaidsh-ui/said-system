from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, Invoice, Matter, Notification, Task, User
from app.routes.helpers import get_form_context, int_or_none, none_if_empty, parse_date
from app.services.auth import ensure_role, get_current_user
from app.services.tasks import create_notification, generate_automatic_tasks, scoped_task_statement
from app.templating import templates

router = APIRouter(prefix="/tasks", tags=["tasks"])


def open_statuses() -> set[str]:
    return {"new", "pending", "in_progress", "overdue"}


def task_for_user_or_404(db: Session, task_id: int, user: User) -> Task:
    stmt = scoped_task_statement(user).where(Task.id == task_id)
    task = db.scalar(stmt)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="المهمة غير موجودة أو ليست ضمن صلاحياتك")
    return task


def filtered_tasks(
    db: Session,
    user: User,
    *,
    q: str | None,
    assigned_to_id: int | None,
    role: str | None,
    task_type: str | None,
    task_status: str | None,
    priority: str | None,
    client_id: int | None,
    matter_id: int | None,
    invoice_id: int | None,
    due_from: str | None,
    due_to: str | None,
) -> list[Task]:
    stmt = scoped_task_statement(user)
    if q:
        like = f"%{q}%"
        stmt = stmt.outerjoin(Client, Task.client_id == Client.id).outerjoin(Matter, Task.matter_id == Matter.id)
        stmt = stmt.where(
            or_(
                Task.title.ilike(like),
                Task.description.ilike(like),
                Task.notes.ilike(like),
                Client.full_name.ilike(like),
                Matter.case_number.ilike(like),
                Matter.title.ilike(like),
            )
        )
    if assigned_to_id:
        stmt = stmt.where(Task.assigned_to_id == assigned_to_id)
    if role:
        stmt = stmt.where(Task.assigned_role == role)
    if task_type:
        stmt = stmt.where(Task.task_type == task_type)
    if task_status:
        stmt = stmt.where(Task.status == task_status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if client_id:
        stmt = stmt.where(Task.client_id == client_id)
    if matter_id:
        stmt = stmt.where(Task.matter_id == matter_id)
    if invoice_id:
        stmt = stmt.where(Task.invoice_id == invoice_id)
    if due_from:
        stmt = stmt.where(Task.due_date >= parse_date(due_from))
    if due_to:
        stmt = stmt.where(Task.due_date <= parse_date(due_to))
    return db.scalars(stmt.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.priority.desc(), Task.created_at.desc())).unique().all()


def dashboard_context(db: Session, user: User, tasks: list[Task]) -> dict:
    today = date.today()
    open_tasks = [task for task in tasks if task.status in open_statuses()]
    completed = [task for task in tasks if task.status == "completed"]
    overdue = [task for task in tasks if task.status == "overdue" or (task.due_date and task.due_date < today and task.status in open_statuses())]
    urgent = [task for task in open_tasks if task.priority == "urgent"]
    collection = [task for task in open_tasks if task.task_type in {"collection", "invoice_followup"}]
    today_tasks = [task for task in open_tasks if task.due_date == today]

    employee_stats = []
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    for employee in users:
        employee_tasks = [task for task in tasks if task.assigned_to_id == employee.id]
        if not employee_tasks and user.role != "admin":
            continue
        total = len(employee_tasks)
        done = len([task for task in employee_tasks if task.status == "completed"])
        late = len([task for task in employee_tasks if task.status == "overdue" or (task.due_date and task.due_date < today and task.status in open_statuses())])
        employee_stats.append(
            {
                "employee": employee,
                "open": len([task for task in employee_tasks if task.status in open_statuses()]),
                "completed": done,
                "overdue": late,
                "completion_rate": round((done / total) * 100) if total else 0,
            }
        )

    notification_stmt = select(Notification).order_by(Notification.created_at.desc()).limit(10)
    if user.role != "admin":
        notification_stmt = notification_stmt.where(Notification.user_id == user.id)
    notifications = db.scalars(notification_stmt).all()
    return {
        "today": today,
        "stats": {
            "open": len(open_tasks),
            "completed": len(completed),
            "overdue": len(overdue),
            "urgent": len(urgent),
            "collection": len(collection),
            "today": len(today_tasks),
        },
        "today_tasks": today_tasks[:8],
        "overdue_tasks": overdue[:8],
        "urgent_tasks": urgent[:8],
        "collection_tasks": collection[:8],
        "employee_stats": employee_stats,
        "notifications": notifications,
    }


@router.get("")
def tasks_index(
    request: Request,
    q: str | None = None,
    assigned_to_id: str | None = None,
    role: str | None = None,
    task_type: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    client_id: str | None = None,
    matter_id: str | None = None,
    invoice_id: str | None = None,
    due_from: str | None = None,
    due_to: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_assigned_to_id = int_or_none(assigned_to_id)
    parsed_client_id = int_or_none(client_id)
    parsed_matter_id = int_or_none(matter_id)
    parsed_invoice_id = int_or_none(invoice_id)
    generate_automatic_tasks(db)
    tasks = filtered_tasks(
        db,
        user,
        q=q,
        assigned_to_id=parsed_assigned_to_id,
        role=role,
        task_type=task_type,
        task_status=status,
        priority=priority,
        client_id=parsed_client_id,
        matter_id=parsed_matter_id,
        invoice_id=parsed_invoice_id,
        due_from=due_from,
        due_to=due_to,
    )
    return templates.TemplateResponse(
        "tasks/index.html",
        {
            "request": request,
            "user": user,
            "tasks": tasks,
            "all_tasks": tasks,
            **dashboard_context(db, user, tasks),
            **get_form_context(db),
            "filters": {
                "q": q or "",
                "assigned_to_id": assigned_to_id or "",
                "role": role or "",
                "task_type": task_type or "",
                "status": status or "",
                "priority": priority or "",
                "client_id": client_id or "",
                "matter_id": matter_id or "",
                "invoice_id": invoice_id or "",
                "due_from": due_from or "",
                "due_to": due_to or "",
            },
        },
    )


@router.get("/new")
def task_new(
    request: Request,
    matter_id: str | None = None,
    client_id: str | None = None,
    invoice_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "accountant", "data_entry"})
    parsed_matter_id = int_or_none(matter_id)
    parsed_client_id = int_or_none(client_id)
    parsed_invoice_id = int_or_none(invoice_id)
    invoice = db.get(Invoice, parsed_invoice_id) if parsed_invoice_id else None
    matter = db.get(Matter, parsed_matter_id) if parsed_matter_id else None
    prefill = {
        "matter_id": parsed_matter_id or (invoice.matter_id if invoice else ""),
        "client_id": parsed_client_id or (invoice.client_id if invoice else matter.client_id if matter else ""),
        "invoice_id": parsed_invoice_id or "",
    }
    return templates.TemplateResponse(
        "tasks/form.html",
        {"request": request, "user": user, "task": None, "prefill": prefill, **get_form_context(db)},
    )


@router.post("/new")
def task_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    task_type: str = Form("internal_reminder"),
    matter_id: str = Form(""),
    client_id: str = Form(""),
    invoice_id: str = Form(""),
    assigned_to_id: str = Form(""),
    assigned_role: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("medium"),
    task_status: str = Form("new"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "accountant", "data_entry"})
    completed_at = datetime.now() if task_status == "completed" else None
    task = Task(
        title=title,
        description=none_if_empty(description),
        task_type=task_type,
        matter_id=int_or_none(matter_id),
        client_id=int_or_none(client_id),
        invoice_id=int_or_none(invoice_id),
        assigned_to_id=int_or_none(assigned_to_id),
        assigned_role=none_if_empty(assigned_role),
        due_date=parse_date(due_date),
        priority=priority,
        status=task_status,
        notes=none_if_empty(notes),
        source="manual",
        created_by_id=user.id,
        completed_at=completed_at,
    )
    db.add(task)
    db.flush()
    create_notification(
        db,
        user_id=task.assigned_to_id,
        task=task,
        title="مهمة يدوية جديدة",
        message=task.title,
        notification_type="task_created",
        source_key=f"manual_task_created:{task.id}",
    )
    db.commit()
    return RedirectResponse("/tasks", status_code=303)


@router.get("/{task_id}/edit")
def task_edit(request: Request, task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "accountant", "data_entry"})
    task = task_for_user_or_404(db, task_id, user)
    return templates.TemplateResponse(
        "tasks/form.html",
        {"request": request, "user": user, "task": task, "prefill": {}, **get_form_context(db)},
    )


@router.post("/{task_id}/edit")
def task_update(
    request: Request,
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    task_type: str = Form("internal_reminder"),
    matter_id: str = Form(""),
    client_id: str = Form(""),
    invoice_id: str = Form(""),
    assigned_to_id: str = Form(""),
    assigned_role: str = Form(""),
    due_date: str = Form(""),
    priority: str = Form("medium"),
    task_status: str = Form("new"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"lawyer", "secretary", "accountant", "data_entry"})
    task = task_for_user_or_404(db, task_id, user)
    old_status = task.status
    task.title = title
    task.description = none_if_empty(description)
    task.task_type = task_type
    task.matter_id = int_or_none(matter_id)
    task.client_id = int_or_none(client_id)
    task.invoice_id = int_or_none(invoice_id)
    task.assigned_to_id = int_or_none(assigned_to_id)
    task.assigned_role = none_if_empty(assigned_role)
    task.due_date = parse_date(due_date)
    task.priority = priority
    task.status = task_status
    task.notes = none_if_empty(notes)
    if task_status == "completed" and old_status != "completed":
        task.completed_at = datetime.now()
    elif task_status != "completed":
        task.completed_at = None
    db.commit()
    return RedirectResponse("/tasks", status_code=303)


@router.post("/{task_id}/complete")
def task_complete(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "accountant", "data_entry"})
    task = task_for_user_or_404(db, task_id, user)
    task.status = "completed"
    task.completed_at = datetime.now()
    db.commit()
    return RedirectResponse("/tasks", status_code=303)


@router.post("/notifications/{notification_id}/read")
def notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notification = db.get(Notification, notification_id)
    if not notification or (notification.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الإشعار غير موجود")
    notification.status = "read"
    notification.read_at = datetime.now()
    db.commit()
    return RedirectResponse("/tasks", status_code=303)

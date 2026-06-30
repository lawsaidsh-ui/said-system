from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Appointment, AuditLog, CaseFee, Client, Consultation, CourtSession, Invoice, Matter, Payment, Task, User
from app.services.audit import recent_audit_logs
from app.services.auth import get_current_user
from app.templating import templates

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


OPEN_MATTER_STATUSES = ["new", "open", "in_progress", "waiting", "court_session"]


def admin_dashboard(db: Session, today: date, week_end: date) -> dict:
    month_start = today.replace(day=1)
    productivity_start = today - timedelta(days=30)
    overdue_invoice_statuses = ["unpaid", "partially_paid"]
    active_users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.role, User.full_name)).all()
    productivity_rows = []
    inactive_users_30 = 0
    for employee in active_users:
        open_tasks = db.scalar(
            select(func.count(Task.id)).where(Task.assigned_to_id == employee.id, Task.status != "completed")
        ) or 0
        overdue_tasks = db.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_id == employee.id,
                Task.due_date < today,
                Task.status != "completed",
            )
        ) or 0
        completed_tasks_30 = db.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_id == employee.id,
                Task.status == "completed",
                Task.completed_at >= productivity_start,
            )
        ) or 0
        assigned_matters = db.scalar(
            select(func.count(Matter.id)).where(
                Matter.assigned_lawyer_id == employee.id,
                Matter.status.in_(OPEN_MATTER_STATUSES),
            )
        ) or 0
        audit_actions_30 = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.user_id == employee.id,
                AuditLog.created_at >= productivity_start,
            )
        ) or 0
        last_activity = db.scalar(select(func.max(AuditLog.created_at)).where(AuditLog.user_id == employee.id))
        if not audit_actions_30:
            inactive_users_30 += 1
        workload = open_tasks + completed_tasks_30
        completion_rate = round((completed_tasks_30 / workload) * 100) if workload else 0
        productivity_rows.append(
            {
                "user": employee,
                "open_tasks": open_tasks,
                "overdue_tasks": overdue_tasks,
                "completed_tasks_30": completed_tasks_30,
                "assigned_matters": assigned_matters,
                "audit_actions_30": audit_actions_30,
                "last_activity": last_activity,
                "completion_rate": completion_rate,
            }
        )

    productivity_rows.sort(
        key=lambda row: (
            row["overdue_tasks"],
            row["open_tasks"],
            row["completed_tasks_30"],
            row["audit_actions_30"],
        ),
        reverse=True,
    )

    completed_tasks_30 = db.scalar(
        select(func.count(Task.id)).where(Task.status == "completed", Task.completed_at >= productivity_start)
    ) or 0
    audit_actions_30 = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.created_at >= productivity_start)) or 0
    unassigned_open_matters = db.scalar(
        select(func.count(Matter.id)).where(
            Matter.status.in_(OPEN_MATTER_STATUSES),
            Matter.assigned_lawyer_id.is_(None),
        )
    ) or 0
    unassigned_open_tasks = db.scalar(
        select(func.count(Task.id)).where(
            Task.status != "completed",
            Task.assigned_to_id.is_(None),
        )
    ) or 0
    return {
        "stats": {
            "clients": db.scalar(select(func.count(Client.id))) or 0,
            "open_matters": db.scalar(select(func.count(Matter.id)).where(Matter.status.in_(OPEN_MATTER_STATUSES))) or 0,
            "week_sessions": db.scalar(select(func.count(CourtSession.id)).where(CourtSession.session_date.between(today, week_end))) or 0,
            "overdue_tasks": db.scalar(select(func.count(Task.id)).where(Task.due_date < today, Task.status != "completed")) or 0,
            "unpaid_invoices": db.scalar(select(func.count(Invoice.id)).where(Invoice.status.in_(["unpaid", "partially_paid"]))) or 0,
            "month_payments": db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.payment_date >= month_start)) or 0,
            "pending_appointments": db.scalar(select(func.count(Appointment.id)).where(Appointment.status == "pending")) or 0,
            "new_consultations": db.scalar(select(func.count(Consultation.id)).where(Consultation.status.in_(["new", "assigned"]))) or 0,
            "active_users": db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0,
            "month_clients": db.scalar(select(func.count(Client.id)).where(Client.created_at >= month_start)) or 0,
            "urgent_tasks": db.scalar(select(func.count(Task.id)).where(Task.priority == "urgent", Task.status != "completed")) or 0,
            "completed_tasks_30": completed_tasks_30,
            "audit_actions_30": audit_actions_30,
            "inactive_users_30": inactive_users_30,
            "unassigned_open_matters": unassigned_open_matters,
            "unassigned_open_tasks": unassigned_open_tasks,
            "overdue_invoice_amount": db.scalar(
                select(func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0)).where(
                    Invoice.due_date < today,
                    Invoice.status.in_(overdue_invoice_statuses),
                )
            )
            or 0,
        },
        "recent_clients": db.scalars(select(Client).order_by(Client.created_at.desc()).limit(5)).all(),
        "recent_matters": db.scalars(
            select(Matter).options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer)).order_by(Matter.created_at.desc()).limit(5)
        ).all(),
        "priority_tasks": db.scalars(
            select(Task)
            .options(selectinload(Task.assigned_to), selectinload(Task.client), selectinload(Task.matter))
            .where(Task.status != "completed")
            .order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.priority.desc())
            .limit(8)
        ).all(),
        "pending_appointments": db.scalars(
            select(Appointment)
            .where(Appointment.status == "pending")
            .order_by(Appointment.appointment_date.asc(), Appointment.appointment_time.asc())
            .limit(6)
        ).all(),
        "new_consultations": db.scalars(
            select(Consultation)
            .options(selectinload(Consultation.client), selectinload(Consultation.assigned_lawyer))
            .where(Consultation.status.in_(["new", "assigned"]))
            .order_by(Consultation.created_at.desc())
            .limit(6)
        ).all(),
        "overdue_invoices": db.scalars(
            select(Invoice)
            .options(selectinload(Invoice.client), selectinload(Invoice.matter))
            .where(Invoice.due_date < today, Invoice.status.in_(overdue_invoice_statuses))
            .order_by(Invoice.due_date.asc())
            .limit(6)
        ).all(),
        "upcoming_sessions": db.scalars(
            select(CourtSession)
            .options(selectinload(CourtSession.matter).selectinload(Matter.client))
            .where(CourtSession.session_date >= today)
            .order_by(CourtSession.session_date)
            .limit(8)
        ).all(),
        "today_tasks": db.scalars(
            select(Task).options(selectinload(Task.assigned_to)).where(Task.due_date == today).order_by(Task.priority.desc()).limit(8)
        ).all(),
        "productivity_rows": productivity_rows,
        "audit_logs": recent_audit_logs(db, limit=8),
    }


def lawyer_dashboard(db: Session, user: User, today: date, week_end: date) -> dict:
    assigned_filter = Matter.assigned_lawyer_id == user.id
    return {
        "stats": {
            "assigned_matters": db.scalar(select(func.count(Matter.id)).where(assigned_filter, Matter.status.in_(OPEN_MATTER_STATUSES))) or 0,
            "week_sessions": db.scalar(
                select(func.count(CourtSession.id)).join(Matter).where(assigned_filter, CourtSession.session_date.between(today, week_end))
            )
            or 0,
            "pending_tasks": db.scalar(select(func.count(Task.id)).where(Task.assigned_to_id == user.id, Task.status != "completed")) or 0,
            "urgent_tasks": db.scalar(select(func.count(Task.id)).where(Task.assigned_to_id == user.id, Task.priority == "urgent", Task.status != "completed")) or 0,
        },
        "my_matters": db.scalars(
            select(Matter)
            .options(selectinload(Matter.client))
            .where(assigned_filter)
            .order_by(Matter.priority.desc(), Matter.created_at.desc())
            .limit(8)
        ).all(),
        "my_sessions": db.scalars(
            select(CourtSession)
            .join(Matter)
            .options(selectinload(CourtSession.matter).selectinload(Matter.client))
            .where(assigned_filter, CourtSession.session_date >= today)
            .order_by(CourtSession.session_date)
            .limit(8)
        ).all(),
        "my_tasks": db.scalars(
            select(Task)
            .options(selectinload(Task.matter), selectinload(Task.client))
            .where(Task.assigned_to_id == user.id, Task.status != "completed")
            .order_by(Task.due_date.is_(None), Task.due_date.asc())
            .limit(8)
        ).all(),
    }


def secretary_dashboard(db: Session, user: User, today: date, week_end: date) -> dict:
    return {
        "stats": {
            "clients": db.scalar(select(func.count(Client.id))) or 0,
            "week_sessions": db.scalar(select(func.count(CourtSession.id)).where(CourtSession.session_date.between(today, week_end))) or 0,
            "new_consultations": db.scalar(select(func.count(Consultation.id)).where(Consultation.status.in_(["new", "assigned"]))) or 0,
            "my_pending_tasks": db.scalar(select(func.count(Task.id)).where(Task.assigned_to_id == user.id, Task.status != "completed")) or 0,
        },
        "recent_clients": db.scalars(select(Client).order_by(Client.created_at.desc()).limit(8)).all(),
        "upcoming_sessions": db.scalars(
            select(CourtSession)
            .options(selectinload(CourtSession.matter).selectinload(Matter.client))
            .where(CourtSession.session_date >= today)
            .order_by(CourtSession.session_date)
            .limit(10)
        ).all(),
        "my_tasks": db.scalars(
            select(Task)
            .options(selectinload(Task.client), selectinload(Task.matter))
            .where(Task.assigned_to_id == user.id, Task.status != "completed")
            .order_by(Task.due_date.is_(None), Task.due_date.asc())
            .limit(8)
        ).all(),
        "consultations": db.scalars(
            select(Consultation).options(selectinload(Consultation.client), selectinload(Consultation.assigned_lawyer)).order_by(Consultation.created_at.desc()).limit(8)
        ).all(),
    }


def accountant_dashboard(db: Session, user: User, today: date) -> dict:
    today = date.today()
    month_start = today.replace(day=1)
    return {
        "stats": {
            "unpaid_invoices": db.scalar(select(func.count(Invoice.id)).where(Invoice.status.in_(["unpaid", "partially_paid"]))) or 0,
            "overdue_invoices": db.scalar(select(func.count(Invoice.id)).where(Invoice.due_date < today, Invoice.status.in_(["unpaid", "partially_paid"]))) or 0,
            "month_payments": db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.payment_date >= month_start)) or 0,
            "my_pending_tasks": db.scalar(select(func.count(Task.id)).where(Task.assigned_to_id == user.id, Task.status != "completed")) or 0,
            "missing_case_fees": db.scalar(
                select(func.count(Matter.id)).where(
                    ~select(CaseFee.id)
                    .where(CaseFee.matter_id == Matter.id, CaseFee.is_cancelled.is_(False))
                    .exists()
                )
            )
            or 0,
        },
        "unpaid_invoices": db.scalars(
            select(Invoice).options(selectinload(Invoice.client), selectinload(Invoice.matter)).where(Invoice.status.in_(["unpaid", "partially_paid"])).order_by(Invoice.due_date.asc()).limit(10)
        ).all(),
        "recent_payments": db.scalars(
            select(Payment).options(selectinload(Payment.invoice).selectinload(Invoice.client)).order_by(Payment.payment_date.desc()).limit(10)
        ).all(),
        "my_tasks": db.scalars(
            select(Task).options(selectinload(Task.client), selectinload(Task.matter)).where(Task.assigned_to_id == user.id, Task.status != "completed").order_by(Task.due_date.is_(None), Task.due_date.asc()).limit(8)
        ).all(),
    }


def data_entry_dashboard(db: Session, user: User, today: date, week_end: date) -> dict:
    return {
        "stats": {
            "clients": db.scalar(select(func.count(Client.id))) or 0,
            "open_matters": db.scalar(select(func.count(Matter.id)).where(Matter.status.in_(OPEN_MATTER_STATUSES))) or 0,
            "week_sessions": db.scalar(select(func.count(CourtSession.id)).where(CourtSession.session_date.between(today, week_end))) or 0,
            "my_pending_tasks": db.scalar(select(func.count(Task.id)).where(Task.assigned_to_id == user.id, Task.status != "completed")) or 0,
            "new_consultations": db.scalar(select(func.count(Consultation.id)).where(Consultation.status.in_(["new", "assigned"]))) or 0,
        },
        "recent_clients": db.scalars(select(Client).order_by(Client.created_at.desc()).limit(8)).all(),
        "recent_matters": db.scalars(
            select(Matter)
            .options(selectinload(Matter.client), selectinload(Matter.assigned_lawyer))
            .order_by(Matter.created_at.desc())
            .limit(8)
        ).all(),
        "upcoming_sessions": db.scalars(
            select(CourtSession)
            .options(selectinload(CourtSession.matter).selectinload(Matter.client))
            .where(CourtSession.session_date >= today)
            .order_by(CourtSession.session_date)
            .limit(8)
        ).all(),
        "my_tasks": db.scalars(
            select(Task)
            .options(selectinload(Task.client), selectinload(Task.matter))
            .where(Task.assigned_to_id == user.id, Task.status != "completed")
            .order_by(Task.due_date.is_(None), Task.due_date.asc())
            .limit(8)
        ).all(),
        "recent_consultations": db.scalars(
            select(Consultation)
            .options(selectinload(Consultation.client), selectinload(Consultation.assigned_lawyer))
            .order_by(Consultation.created_at.desc())
            .limit(8)
        ).all(),
    }


def viewer_dashboard(db: Session, today: date, week_end: date) -> dict:
    return {
        "stats": {
            "clients": db.scalar(select(func.count(Client.id))) or 0,
            "open_matters": db.scalar(select(func.count(Matter.id)).where(Matter.status.in_(OPEN_MATTER_STATUSES))) or 0,
            "week_sessions": db.scalar(select(func.count(CourtSession.id)).where(CourtSession.session_date.between(today, week_end))) or 0,
            "unpaid_invoices": db.scalar(select(func.count(Invoice.id)).where(Invoice.status.in_(["unpaid", "partially_paid"]))) or 0,
        },
        "recent_matters": db.scalars(select(Matter).options(selectinload(Matter.client)).order_by(Matter.created_at.desc()).limit(8)).all(),
        "upcoming_sessions": db.scalars(
            select(CourtSession).options(selectinload(CourtSession.matter)).where(CourtSession.session_date >= today).order_by(CourtSession.session_date).limit(8)
        ).all(),
        "recent_invoices": db.scalars(select(Invoice).options(selectinload(Invoice.client)).order_by(Invoice.created_at.desc()).limit(8)).all(),
    }


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role == "accountant":
        return RedirectResponse("/accounting", status_code=303)
    today = date.today()
    week_end = today + timedelta(days=7)
    role = user.role if user.role in {"admin", "lawyer", "secretary", "accountant", "data_entry", "viewer"} else "viewer"
    builders = {
        "admin": lambda: admin_dashboard(db, today, week_end),
        "lawyer": lambda: lawyer_dashboard(db, user, today, week_end),
        "secretary": lambda: secretary_dashboard(db, user, today, week_end),
        "accountant": lambda: accountant_dashboard(db, user, today),
        "data_entry": lambda: data_entry_dashboard(db, user, today, week_end),
        "viewer": lambda: viewer_dashboard(db, today, week_end),
    }
    return templates.TemplateResponse(
        f"dashboard/{role}.html",
        {
            "request": request,
            "user": user,
            "dashboard_role": role,
            **builders[role](),
        },
    )

from datetime import time as _time

from fastapi.templating import Jinja2Templates

from app.services.labels import (
    CASE_STATUSES,
    CLIENT_TYPES,
    CONSULTATION_STATUSES,
    INVOICE_STATUSES,
    PAYMENT_METHODS,
    PRIORITIES,
    ROLE_LABELS,
    SESSION_STATUSES,
    TASK_STATUSES,
    TASK_TYPES,
    badge_class,
    label,
)
from app.services.audit import audit_action_label, audit_entity_label
from app.services.permissions import nav_for_role


def _time12(t: _time) -> str:
    hour = t.hour % 12 or 12
    minute = t.strftime("%M")
    period = "م" if t.hour >= 12 else "ص"
    return f"{hour}:{minute} {period}"


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["time12"] = _time12
templates.env.globals.update(
    role_labels=ROLE_LABELS,
    client_types=CLIENT_TYPES,
    case_statuses=CASE_STATUSES,
    priorities=PRIORITIES,
    session_statuses=SESSION_STATUSES,
    task_statuses=TASK_STATUSES,
    task_types=TASK_TYPES,
    invoice_statuses=INVOICE_STATUSES,
    payment_methods=PAYMENT_METHODS,
    consultation_statuses=CONSULTATION_STATUSES,
    label=label,
    badge_class=badge_class,
    audit_action_label=audit_action_label,
    audit_entity_label=audit_entity_label,
    nav_for_role=nav_for_role,
)

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routes import accounting, appointments, audit, auth, clients, consultations, dashboard, documents, invoices, matters, owner_financial, payments, public, reports, sessions, settings, tasks, users, whatsapp
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
from app.services.schema import ensure_runtime_schema
from app.services.seed import seed_database


settings_obj = get_settings()
app = FastAPI(title=settings_obj.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings_obj.secret_key, max_age=settings_obj.session_max_age)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    with SessionLocal() as db:
        seed_database(db)


@app.middleware("http")
async def add_template_context(request: Request, call_next):
    request.state.app_name = settings_obj.app_name
    return await call_next(request)


for router in [
    public.router,
    auth.router,
    dashboard.router,
    audit.router,
    owner_financial.router,
    accounting.router,
    clients.router,
    matters.router,
    sessions.router,
    tasks.router,
    documents.router,
    invoices.router,
    payments.router,
    appointments.router,
    consultations.router,
    users.router,
    reports.router,
    settings.router,
    whatsapp.router,
]:
    app.include_router(router)


def template_globals() -> dict:
    return {
        "role_labels": ROLE_LABELS,
        "client_types": CLIENT_TYPES,
        "case_statuses": CASE_STATUSES,
        "priorities": PRIORITIES,
        "session_statuses": SESSION_STATUSES,
        "task_statuses": TASK_STATUSES,
        "task_types": TASK_TYPES,
        "invoice_statuses": INVOICE_STATUSES,
        "payment_methods": PAYMENT_METHODS,
        "consultation_statuses": CONSULTATION_STATUSES,
        "label": label,
        "badge_class": badge_class,
    }

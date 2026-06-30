from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.auth import ensure_role, get_current_user
from app.services.owner_financial import build_owner_financial_report, update_owner_settings
from app.templating import templates


router = APIRouter(prefix="/owner-financial", tags=["owner-financial"])


def require_owner(user: User) -> None:
    ensure_role(user, {"admin"})


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def report_filters(
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    service_type: str | None = None,
    lawyer_id: str | None = None,
    collection_status: str | None = None,
    client_source: str | None = None,
) -> dict:
    return {
        "period": period or "month",
        "start_date": parse_date(start_date),
        "end_date": parse_date(end_date),
        "service_type": service_type or "",
        "lawyer_id": lawyer_id or "",
        "collection_status": collection_status or "",
        "client_source": client_source or "",
    }


@router.get("")
def owner_financial_dashboard(
    request: Request,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    service_type: str | None = None,
    lawyer_id: str | None = None,
    collection_status: str | None = None,
    client_source: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_owner(user)
    filters = report_filters(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source)
    report = build_owner_financial_report(db, filters)
    return templates.TemplateResponse(
        "owner_financial/dashboard.html",
        {"request": request, "user": user, "report": report},
    )


@router.post("/settings")
def owner_financial_settings_update(
    monthly_fixed_expenses: str = Form("0"),
    monthly_revenue_target: str = Form("0"),
    monthly_profit_target: str = Form("0"),
    default_profit_margin: str = Form("70"),
    collection_warning_threshold: str = Form("75"),
    expense_warning_threshold: str = Form("15"),
    expense_categories_json: str = Form(""),
    service_categories_json: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_owner(user)
    update_owner_settings(
        db,
        monthly_fixed_expenses=monthly_fixed_expenses,
        monthly_revenue_target=monthly_revenue_target,
        monthly_profit_target=monthly_profit_target,
        default_profit_margin=default_profit_margin,
        collection_warning_threshold=collection_warning_threshold,
        expense_warning_threshold=expense_warning_threshold,
        expense_categories_json=expense_categories_json,
        service_categories_json=service_categories_json,
    )
    return RedirectResponse("/owner-financial", status_code=303)


def _api_report(
    period: str | None,
    start_date: str | None,
    end_date: str | None,
    service_type: str | None,
    lawyer_id: str | None,
    collection_status: str | None,
    client_source: str | None,
    db: Session,
    user: User,
) -> dict:
    require_owner(user)
    return build_owner_financial_report(
        db,
        report_filters(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source),
    )


@router.get("/api/summary")
def api_summary(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["summary"]


@router.get("/api/break-even")
def api_break_even(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["break_even"]


@router.get("/api/revenues")
def api_revenues(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["revenues"]


@router.get("/api/expenses")
def api_expenses(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["expenses"]


@router.get("/api/collection-status")
def api_collection_status(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["collection"]


@router.get("/api/service-profitability")
def api_service_profitability(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["service_profitability"]


@router.get("/api/monthly-forecast")
def api_monthly_forecast(period: str | None = None, start_date: str | None = None, end_date: str | None = None, service_type: str | None = None, lawyer_id: str | None = None, collection_status: str | None = None, client_source: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _api_report(period, start_date, end_date, service_type, lawyer_id, collection_status, client_source, db, user)["forecast"]


@router.get("/api/settings")
def api_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_owner(user)
    report = build_owner_financial_report(db, {"period": "month"})
    settings = report["settings"]
    return {
        "monthly_fixed_expenses": settings.monthly_fixed_expenses,
        "monthly_revenue_target": settings.monthly_revenue_target,
        "monthly_profit_target": settings.monthly_profit_target,
        "default_profit_margin": settings.default_profit_margin,
        "collection_warning_threshold": settings.collection_warning_threshold,
        "expense_warning_threshold": settings.expense_warning_threshold,
        "expense_categories_json": settings.expense_categories_json,
        "service_categories_json": settings.service_categories_json,
    }

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Agency,
    CaseFee,
    Client,
    Consultation,
    CourtSession,
    Document,
    Expense,
    FixedMonthlyExpense,
    Installment,
    Invoice,
    Matter,
    PaymentVoucher,
    ReceiptVoucher,
    Task,
    User,
    WhatsAppLog,
)


DB_PATH = ROOT / "saeed_law.db"
DEMO_PATTERNS = [
    "test",
    "demo",
    "sample",
    "example.test",
    "saeed-law.test",
    "deleted.local",
    "تجريبي",
    "تجريبية",
    "اختبار",
    "قضية تجريبية",
    "عميل تجريبي",
]
DEMO_USER_EMAILS = {
    "lawyer@saeed-law.test",
    "secretary@saeed-law.test",
    "accountant@saeed-law.test",
    "viewer@saeed-law.test",
    "data-entry@saeed-law.test",
}
ADMIN_EMAIL = "admin@saeed-law.test"


def normalized(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def has_demo_marker(*values: object) -> bool:
    text = " ".join(normalized(value) for value in values)
    return any(pattern.lower() in text for pattern in DEMO_PATTERNS)


def backup_database() -> Path | None:
    if not DB_PATH.exists():
        return None
    backup_path = ROOT / f"saeed_law.backup-before-clean-demo-data-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def delete_matter_tree(db, matter: Matter) -> dict[str, int]:
    counts: dict[str, int] = {}
    matter_id = matter.id
    related_models = [
        CourtSession,
        Task,
        Document,
        Invoice,
        Agency,
        WhatsAppLog,
        CaseFee,
        ReceiptVoucher,
        PaymentVoucher,
        Expense,
        Installment,
    ]
    for model in related_models:
        rows = db.scalars(select(model).where(model.matter_id == matter_id)).all()
        counts[model.__name__] = counts.get(model.__name__, 0) + len(rows)
        for row in rows:
            db.delete(row)
    db.delete(matter)
    counts["Matter"] = counts.get("Matter", 0) + 1
    return counts


def merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def clean_demo_data() -> dict[str, int | str]:
    backup_path = backup_database()
    counts: dict[str, int | str] = {"backup": str(backup_path or "not-created")}
    now = datetime.now(UTC).replace(tzinfo=None)

    with SessionLocal() as db:
        demo_matters = [
            matter
            for matter in db.scalars(select(Matter).order_by(Matter.id)).all()
            if has_demo_marker(
                matter.case_number,
                matter.ministry_case_number,
                matter.title,
                matter.description,
                matter.case_type,
                matter.court_name,
                matter.opponent_name,
            )
        ]
        for matter in demo_matters:
            merge_counts(counts, delete_matter_tree(db, matter))

        demo_clients = [
            client
            for client in db.scalars(select(Client).order_by(Client.id)).all()
            if has_demo_marker(
                client.full_name,
                client.email,
                client.phone,
                client.civil_id,
                client.company_name,
                client.commercial_registration,
                client.notes,
            )
        ]
        for client in demo_clients:
            for matter in list(client.matters):
                merge_counts(counts, delete_matter_tree(db, matter))
            related_models = [Task, Document, Invoice, Consultation, WhatsAppLog, CaseFee, ReceiptVoucher, Installment]
            for model in related_models:
                rows = db.scalars(select(model).where(model.client_id == client.id)).all()
                counts[model.__name__] = int(counts.get(model.__name__, 0)) + len(rows)
                for row in rows:
                    db.delete(row)
            db.delete(client)
            counts["Client"] = int(counts.get("Client", 0)) + 1

        demo_tasks = [
            task
            for task in db.scalars(select(Task).order_by(Task.id)).all()
            if has_demo_marker(task.title, task.description, task.notes, task.source, task.source_key)
        ]
        for task in demo_tasks:
            db.delete(task)
        counts["Task"] = int(counts.get("Task", 0)) + len(demo_tasks)

        demo_expenses = [
            expense
            for expense in db.scalars(select(Expense).order_by(Expense.id)).all()
            if has_demo_marker(expense.category, expense.notes, expense.attachment_url)
        ]
        for expense in demo_expenses:
            db.delete(expense)
        counts["Expense"] = int(counts.get("Expense", 0)) + len(demo_expenses)

        demo_fixed_expenses = [
            expense
            for expense in db.scalars(select(FixedMonthlyExpense).order_by(FixedMonthlyExpense.id)).all()
            if has_demo_marker(expense.title, expense.category, expense.vendor_name, expense.notes)
        ]
        for expense in demo_fixed_expenses:
            db.delete(expense)
        counts["FixedMonthlyExpense"] = int(counts.get("FixedMonthlyExpense", 0)) + len(demo_fixed_expenses)

        for user in db.scalars(select(User).order_by(User.id)).all():
            if user.email == ADMIN_EMAIL:
                continue
            if user.deleted_at is not None:
                continue
            if user.email in DEMO_USER_EMAILS or has_demo_marker(user.full_name, user.email, user.phone):
                user.is_active = False
                user.deleted_at = user.deleted_at or now
                user.email = f"deleted-demo-user-{user.id}-{int(now.timestamp())}@deleted.local"
                user.phone = None
                counts["User"] = int(counts.get("User", 0)) + 1

        db.commit()

    return counts


def main() -> None:
    counts = clean_demo_data()
    for key, value in counts.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()

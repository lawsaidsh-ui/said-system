from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys

from sqlalchemy import select, update
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import (
    Agency,
    CaseFee,
    CourtSession,
    Document,
    Expense,
    Installment,
    Invoice,
    Matter,
    PaymentVoucher,
    ReceiptVoucher,
    Task,
    WhatsAppLog,
)


DB_PATH = ROOT / "saeed_law.db"


def normalize_text(value: str | None) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return value


def matter_signature(matter: Matter) -> tuple:
    ministry_case_number = normalize_text(matter.ministry_case_number)
    if ministry_case_number:
        return ("ministry", ministry_case_number)
    return (
        "manual",
        matter.client_id,
        normalize_text(matter.title),
        normalize_text(matter.case_type),
        normalize_text(matter.court_name),
        normalize_text(matter.opponent_name),
        matter.opened_at.isoformat() if matter.opened_at else "",
        str(matter.claim_amount or "0"),
    )


def backup_database() -> Path | None:
    if not DB_PATH.exists():
        return None
    backup_path = ROOT / f"saeed_law.backup-before-delete-duplicate-matters-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def reassign_related_rows(db: Session, duplicate_id: int, keeper_id: int) -> int:
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
    updated = 0
    for model in related_models:
        result = db.execute(update(model).where(model.matter_id == duplicate_id).values(matter_id=keeper_id))
        updated += result.rowcount or 0
    return updated


def delete_duplicate_matters(db: Session) -> tuple[int, int]:
    matters = db.scalars(select(Matter).order_by(Matter.id)).all()
    groups: dict[tuple, list[Matter]] = defaultdict(list)
    for matter in matters:
        signature = matter_signature(matter)
        if signature[0] == "manual" and not signature[2]:
            continue
        groups[signature].append(matter)

    deleted = 0
    reassigned = 0
    for rows in groups.values():
        if len(rows) < 2:
            continue
        keeper = rows[0]
        for duplicate in rows[1:]:
            reassigned += reassign_related_rows(db, duplicate.id, keeper.id)
            db.delete(duplicate)
            deleted += 1
    return deleted, reassigned


def main() -> None:
    backup_path = backup_database()
    with SessionLocal() as db:
        deleted, reassigned = delete_duplicate_matters(db)
        db.commit()
    print(f"backup={backup_path or 'not-created'}")
    print(f"deleted_duplicate_matters={deleted}")
    print(f"reassigned_related_rows={reassigned}")


if __name__ == "__main__":
    main()

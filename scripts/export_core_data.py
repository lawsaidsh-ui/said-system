from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Client, Matter, Task


OUTPUT_PATH = ROOT / "core_data_export.json"


def encode_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def row_dict(row, columns: list[str]) -> dict:
    return {column: encode_value(getattr(row, column)) for column in columns}


def main() -> None:
    client_columns = [
        "id",
        "full_name",
        "phone",
        "email",
        "civil_id",
        "address",
        "client_type",
        "company_name",
        "commercial_registration",
        "notes",
    ]
    matter_columns = [
        "id",
        "case_number",
        "ministry_case_number",
        "title",
        "client_id",
        "assigned_lawyer_id",
        "case_type",
        "court_name",
        "court_level",
        "opponent_name",
        "opponent_phone",
        "status",
        "priority",
        "description",
        "claim_amount",
        "opened_at",
        "closed_at",
        "appeal_deadline",
        "cassation_deadline",
    ]
    task_columns = [
        "id",
        "title",
        "description",
        "task_type",
        "matter_id",
        "client_id",
        "invoice_id",
        "assigned_to_id",
        "assigned_role",
        "due_date",
        "priority",
        "status",
        "notes",
        "source",
        "source_key",
        "created_by_id",
        "completed_at",
    ]
    with SessionLocal() as db:
        payload = {
            "clients": [row_dict(row, client_columns) for row in db.scalars(select(Client).order_by(Client.id)).all()],
            "matters": [row_dict(row, matter_columns) for row in db.scalars(select(Matter).order_by(Matter.id)).all()],
            "tasks": [row_dict(row, task_columns) for row in db.scalars(select(Task).order_by(Task.id)).all()],
        }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported={OUTPUT_PATH}")
    print(f"clients={len(payload['clients'])}")
    print(f"matters={len(payload['matters'])}")
    print(f"tasks={len(payload['tasks'])}")


if __name__ == "__main__":
    main()

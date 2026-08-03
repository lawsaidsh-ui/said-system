from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Client, Matter, Task


def parse_date(value: str | None):
    return date.fromisoformat(value) if value else None


def parse_datetime(value: str | None):
    return datetime.fromisoformat(value) if value else None


def parse_decimal(value: str | None):
    return Decimal(value) if value not in (None, "") else Decimal("0")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import missing clients, matters, and tasks from core_data_export.json.")
    parser.add_argument("input", nargs="?", default="core_data_export.json")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag the script only prints a dry-run.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    with SessionLocal() as db:
        existing_clients_by_name = {client.full_name.strip(): client for client in db.scalars(select(Client)).all()}
        client_id_map: dict[int, int] = {}
        created_clients = 0
        for item in payload.get("clients", []):
            original_id = int(item["id"])
            existing = existing_clients_by_name.get((item.get("full_name") or "").strip())
            if existing:
                client_id_map[original_id] = existing.id
                continue
            client = Client(
                full_name=item["full_name"],
                phone=item.get("phone"),
                email=item.get("email"),
                civil_id=item.get("civil_id"),
                address=item.get("address"),
                client_type=item.get("client_type") or "individual",
                company_name=item.get("company_name"),
                commercial_registration=item.get("commercial_registration"),
                notes=item.get("notes"),
            )
            db.add(client)
            db.flush()
            existing_clients_by_name[client.full_name.strip()] = client
            client_id_map[original_id] = client.id
            created_clients += 1

        existing_matters_by_number = {}
        existing_matters_by_ministry = {}
        for matter in db.scalars(select(Matter)).all():
            existing_matters_by_number[matter.case_number] = matter
            if matter.ministry_case_number:
                existing_matters_by_ministry[matter.ministry_case_number] = matter
        matter_id_map: dict[int, int] = {}
        created_matters = 0
        for item in payload.get("matters", []):
            original_id = int(item["id"])
            existing = existing_matters_by_number.get(item.get("case_number"))
            if not existing and item.get("ministry_case_number"):
                existing = existing_matters_by_ministry.get(item["ministry_case_number"])
            if existing:
                matter_id_map[original_id] = existing.id
                continue
            client_id = client_id_map.get(int(item["client_id"]))
            if not client_id:
                continue
            matter = Matter(
                case_number=item["case_number"],
                ministry_case_number=item.get("ministry_case_number"),
                title=item["title"],
                client_id=client_id,
                assigned_lawyer_id=None,
                case_type=item.get("case_type"),
                court_name=item.get("court_name"),
                court_level=item.get("court_level"),
                opponent_name=item.get("opponent_name"),
                opponent_phone=item.get("opponent_phone"),
                status=item.get("status") or "new",
                priority=item.get("priority") or "medium",
                description=item.get("description"),
                claim_amount=parse_decimal(item.get("claim_amount")),
                opened_at=parse_date(item.get("opened_at")),
                closed_at=parse_date(item.get("closed_at")),
                appeal_deadline=parse_date(item.get("appeal_deadline")),
                cassation_deadline=parse_date(item.get("cassation_deadline")),
            )
            db.add(matter)
            db.flush()
            existing_matters_by_number[matter.case_number] = matter
            if matter.ministry_case_number:
                existing_matters_by_ministry[matter.ministry_case_number] = matter
            matter_id_map[original_id] = matter.id
            created_matters += 1

        existing_task_keys = {task.source_key for task in db.scalars(select(Task)).all() if task.source_key}
        created_tasks = 0
        for item in payload.get("tasks", []):
            source_key = item.get("source_key")
            if source_key and source_key in existing_task_keys:
                continue
            client_id = client_id_map.get(int(item["client_id"])) if item.get("client_id") else None
            matter_id = matter_id_map.get(int(item["matter_id"])) if item.get("matter_id") else None
            if item.get("client_id") and not client_id:
                continue
            if item.get("matter_id") and not matter_id:
                continue
            task = Task(
                title=item["title"],
                description=item.get("description"),
                task_type=item.get("task_type") or "internal_reminder",
                matter_id=matter_id,
                client_id=client_id,
                invoice_id=None,
                assigned_to_id=None,
                assigned_role=item.get("assigned_role"),
                due_date=parse_date(item.get("due_date")),
                priority=item.get("priority") or "medium",
                status=item.get("status") or "new",
                notes=item.get("notes"),
                source=item.get("source") or "manual",
                source_key=source_key,
                created_by_id=None,
                completed_at=parse_datetime(item.get("completed_at")),
            )
            db.add(task)
            created_tasks += 1

        print(f"created_clients={created_clients}")
        print(f"created_matters={created_matters}")
        print(f"created_tasks={created_tasks}")
        if args.apply:
            db.commit()
            print("committed=true")
        else:
            db.rollback()
            print("committed=false")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine, func, select, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Base
from app.models import Client, Matter, Task
from app.services.schema import ensure_runtime_schema


SOURCE_URL = f"sqlite:///{(ROOT / 'saeed_law.db').resolve().as_posix()}"
BACKUP_DIR = ROOT / "database_backups"


def encode_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def backup_target(target_engine) -> Path:
    BACKUP_DIR.mkdir(exist_ok=True)
    backup_path = BACKUP_DIR / f"postgres-before-local-replace-{datetime.now():%Y%m%d-%H%M%S}.json"
    payload = {}
    with target_engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = conn.execute(select(table)).mappings().all()
            payload[table.name] = [
                {column: encode_value(value) for column, value in row.items()}
                for row in rows
            ]
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_path


def table_rows(source_engine, table) -> list[dict]:
    with source_engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(table)).mappings().all()]


def reset_postgres_sequence(conn, table) -> None:
    pk_columns = list(table.primary_key.columns)
    if len(pk_columns) != 1:
        return
    pk = pk_columns[0]
    if pk.type.python_type is not int:
        return
    sequence = conn.execute(
        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
        {"table_name": table.name, "column_name": pk.name},
    ).scalar()
    if not sequence:
        return
    max_id = conn.execute(select(func.coalesce(func.max(pk), 0))).scalar() or 0
    if max_id <= 0:
        conn.execute(text("SELECT setval(:sequence, 1, false)"), {"sequence": sequence})
        return
    conn.execute(text("SELECT setval(:sequence, :value, true)"), {"sequence": sequence, "value": max_id})


def counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            "clients": conn.execute(select(func.count(Client.id))).scalar() or 0,
            "matters": conn.execute(select(func.count(Matter.id))).scalar() or 0,
            "tasks": conn.execute(select(func.count(Task.id))).scalar() or 0,
        }


def main() -> None:
    target_url = os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not target_url:
        raise SystemExit("Set TARGET_DATABASE_URL or DATABASE_URL to the PostgreSQL database URL.")
    if target_url.startswith("postgres://"):
        target_url = target_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif target_url.startswith("postgresql://"):
        target_url = target_url.replace("postgresql://", "postgresql+psycopg://", 1)

    source_engine = create_engine(SOURCE_URL, future=True)
    target_engine = create_engine(target_url, future=True)

    ensure_runtime_schema(target_engine)
    Base.metadata.create_all(bind=target_engine)

    source_counts = counts(source_engine)
    target_counts_before = counts(target_engine)
    backup_path = backup_target(target_engine)

    source_data = {table.name: table_rows(source_engine, table) for table in Base.metadata.sorted_tables}

    with target_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        for table in Base.metadata.sorted_tables:
            rows = source_data[table.name]
            if rows:
                conn.execute(table.insert(), rows)
        if target_engine.dialect.name == "postgresql":
            for table in Base.metadata.sorted_tables:
                reset_postgres_sequence(conn, table)

    target_counts_after = counts(target_engine)
    print(f"backup={backup_path}")
    print(f"source_counts={source_counts}")
    print(f"target_counts_before={target_counts_before}")
    print(f"target_counts_after={target_counts_after}")


if __name__ == "__main__":
    main()

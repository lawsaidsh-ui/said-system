"""add financial date quality fields

Revision ID: 0016_financial_date_quality
Revises: 0015_receipt_allocation_fields
Create Date: 2026-06-27
"""

from calendar import monthrange
from datetime import date, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016_financial_date_quality"
down_revision: Union[str, None] = "0015_receipt_allocation_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


HISTORICAL_START = date(2025, 11, 1)
HISTORICAL_NOTE = "تاريخ تقديري - تم إدخالها من ملفات مالية قديمة بدون تاريخ دفع مؤكد"


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    return None


def _month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def _add_date_quality_columns(table_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    if table_name not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "date_status" not in columns:
        op.add_column(
            table_name,
            sa.Column("date_status", sa.String(20), nullable=False, server_default="confirmed"),
        )
    if "date_note" not in columns:
        op.add_column(table_name, sa.Column("date_note", sa.Text(), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    index_name = f"ix_{table_name}_date_status"
    if index_name not in indexes:
        op.create_index(index_name, table_name, ["date_status"])


def _mark_historical_rows(table_name: str, date_column: str) -> None:
    conn = op.get_bind()
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=conn)
    today = date.today()
    rows = conn.execute(
        sa.select(table.c.id, table.c[date_column], table.c.date_status).where(
            table.c[date_column] >= HISTORICAL_START,
            table.c[date_column] <= today,
        )
    ).mappings()
    for row in rows:
        current_status = (row.get("date_status") or "confirmed").strip()
        if current_status != "confirmed":
            continue
        current_date = _parse_date(row[date_column])
        if not current_date:
            continue
        conn.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                **{
                    date_column: _month_end(current_date),
                    "date_status": "estimated",
                    "date_note": HISTORICAL_NOTE,
                }
            )
        )


def upgrade() -> None:
    targets = {
        "payments": "payment_date",
        "receipt_vouchers": "received_at",
        "expenses": "expense_date",
        "payment_vouchers": "paid_at",
        "journal_entries": "entry_date",
    }
    for table_name in targets:
        _add_date_quality_columns(table_name)
    for table_name, date_column in targets.items():
        _mark_historical_rows(table_name, date_column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table_name in ["journal_entries", "payment_vouchers", "expenses", "receipt_vouchers", "payments"]:
        if table_name not in tables:
            continue
        indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        index_name = f"ix_{table_name}_date_status"
        if index_name in indexes:
            op.drop_index(index_name, table_name=table_name)
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "date_note" in columns:
            op.drop_column(table_name, "date_note")
        if "date_status" in columns:
            op.drop_column(table_name, "date_status")

"""add fixed monthly expenses

Revision ID: 0013_fixed_monthly_expenses
Revises: 0012_payment_voucher_client_matter
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_fixed_monthly_expenses"
down_revision: Union[str, None] = "0012_payment_voucher_client_matter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "fixed_monthly_expenses" not in tables:
        op.create_table(
            "fixed_monthly_expenses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("category", sa.String(120), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("due_day", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("payment_method", sa.String(40), nullable=True),
            sa.Column("vendor_name", sa.String(255), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    indexes = {index["name"] for index in inspector.get_indexes("fixed_monthly_expenses")} if "fixed_monthly_expenses" in tables else set()
    for name, columns in (
        ("ix_fixed_monthly_expenses_title", ["title"]),
        ("ix_fixed_monthly_expenses_category", ["category"]),
        ("ix_fixed_monthly_expenses_vendor_name", ["vendor_name"]),
    ):
        if name not in indexes:
            op.create_index(name, "fixed_monthly_expenses", columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "fixed_monthly_expenses" in set(inspector.get_table_names()):
        op.drop_table("fixed_monthly_expenses")

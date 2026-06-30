"""add receipt allocation fields

Revision ID: 0015_receipt_allocation_fields
Revises: 0014_case_fee_groups
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0015_receipt_allocation_fields"
down_revision: Union[str, None] = "0014_case_fee_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "receipt_vouchers" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("receipt_vouchers")}
    if "case_fee_id" not in columns:
        op.add_column("receipt_vouchers", sa.Column("case_fee_id", sa.Integer(), nullable=True))
    if "receipt_type" not in columns:
        op.add_column("receipt_vouchers", sa.Column("receipt_type", sa.String(40), nullable=False, server_default="case_fee"))
    indexes = {index["name"] for index in inspector.get_indexes("receipt_vouchers")}
    if "ix_receipt_vouchers_case_fee_id" not in indexes:
        op.create_index("ix_receipt_vouchers_case_fee_id", "receipt_vouchers", ["case_fee_id"])
    if "ix_receipt_vouchers_receipt_type" not in indexes:
        op.create_index("ix_receipt_vouchers_receipt_type", "receipt_vouchers", ["receipt_type"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "receipt_vouchers" not in set(inspector.get_table_names()):
        return
    indexes = {index["name"] for index in inspector.get_indexes("receipt_vouchers")}
    if "ix_receipt_vouchers_receipt_type" in indexes:
        op.drop_index("ix_receipt_vouchers_receipt_type", table_name="receipt_vouchers")
    if "ix_receipt_vouchers_case_fee_id" in indexes:
        op.drop_index("ix_receipt_vouchers_case_fee_id", table_name="receipt_vouchers")
    columns = {column["name"] for column in inspector.get_columns("receipt_vouchers")}
    if "receipt_type" in columns:
        op.drop_column("receipt_vouchers", "receipt_type")
    if "case_fee_id" in columns:
        op.drop_column("receipt_vouchers", "case_fee_id")

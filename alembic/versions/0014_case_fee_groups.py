"""add case fee groups

Revision ID: 0014_case_fee_groups
Revises: 0013_fixed_monthly_expenses
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014_case_fee_groups"
down_revision: Union[str, None] = "0013_fixed_monthly_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "case_fees" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("case_fees")}
    if "group_key" not in columns:
        op.add_column("case_fees", sa.Column("group_key", sa.String(80), nullable=True))
    if "group_total_amount" not in columns:
        op.add_column("case_fees", sa.Column("group_total_amount", sa.Numeric(12, 2), nullable=True))
    if "is_group_primary" not in columns:
        op.add_column("case_fees", sa.Column("is_group_primary", sa.Boolean(), nullable=False, server_default=sa.true()))
    indexes = {index["name"] for index in inspector.get_indexes("case_fees")}
    if "ix_case_fees_group_key" not in indexes:
        op.create_index("ix_case_fees_group_key", "case_fees", ["group_key"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "case_fees" not in set(inspector.get_table_names()):
        return
    indexes = {index["name"] for index in inspector.get_indexes("case_fees")}
    if "ix_case_fees_group_key" in indexes:
        op.drop_index("ix_case_fees_group_key", table_name="case_fees")
    columns = {column["name"] for column in inspector.get_columns("case_fees")}
    if "is_group_primary" in columns:
        op.drop_column("case_fees", "is_group_primary")
    if "group_total_amount" in columns:
        op.drop_column("case_fees", "group_total_amount")
    if "group_key" in columns:
        op.drop_column("case_fees", "group_key")

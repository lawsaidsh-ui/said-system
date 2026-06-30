"""add success fee percentage

Revision ID: 0004_success_fee_percentage
Revises: 0003_accounting
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_success_fee_percentage"
down_revision = "0003_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("case_fees")}
    if "success_percentage" not in columns:
        op.add_column("case_fees", sa.Column("success_percentage", sa.Numeric(5, 2), nullable=True))
    if "won_amount" not in columns:
        op.add_column("case_fees", sa.Column("won_amount", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("case_fees")}
    if "won_amount" in columns:
        op.drop_column("case_fees", "won_amount")
    if "success_percentage" in columns:
        op.drop_column("case_fees", "success_percentage")

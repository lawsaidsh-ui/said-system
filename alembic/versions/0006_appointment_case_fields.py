"""add case_type and litigation_degree to appointments

Revision ID: 0006_appointment_case_fields
Revises: 0005_owner_financial_settings
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_appointment_case_fields"
down_revision = "0005_owner_financial_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("appointments")}
    if "case_type" not in existing_cols:
        op.add_column("appointments", sa.Column("case_type", sa.String(120), nullable=True))
    if "litigation_degree" not in existing_cols:
        op.add_column("appointments", sa.Column("litigation_degree", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("appointments", "litigation_degree")
    op.drop_column("appointments", "case_type")

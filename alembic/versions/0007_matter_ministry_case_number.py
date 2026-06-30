"""add ministry case number to matters

Revision ID: 0007_matter_ministry_case_number
Revises: 0006_appointment_case_fields
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_matter_ministry_case_number"
down_revision = "0006_appointment_case_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col["name"] for col in inspector.get_columns("matters")}
    if "ministry_case_number" not in existing_cols:
        op.add_column("matters", sa.Column("ministry_case_number", sa.String(120), nullable=True))

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("matters")}
    if "ix_matters_ministry_case_number" not in existing_indexes:
        op.create_index("ix_matters_ministry_case_number", "matters", ["ministry_case_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_matters_ministry_case_number", table_name="matters")
    op.drop_column("matters", "ministry_case_number")

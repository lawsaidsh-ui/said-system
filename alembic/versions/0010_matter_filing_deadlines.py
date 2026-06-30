"""add matter filing deadline reminders

Revision ID: 0010_matter_filing_deadlines
Revises: 0009_tasks_automation
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_matter_filing_deadlines"
down_revision = "0009_tasks_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("matters")}
    indexes = {index["name"] for index in inspector.get_indexes("matters")}

    if "appeal_deadline" not in columns:
        op.add_column("matters", sa.Column("appeal_deadline", sa.Date(), nullable=True))
    if "cassation_deadline" not in columns:
        op.add_column("matters", sa.Column("cassation_deadline", sa.Date(), nullable=True))
    if "ix_matters_appeal_deadline" not in indexes:
        op.create_index("ix_matters_appeal_deadline", "matters", ["appeal_deadline"])
    if "ix_matters_cassation_deadline" not in indexes:
        op.create_index("ix_matters_cassation_deadline", "matters", ["cassation_deadline"])


def downgrade() -> None:
    with op.batch_alter_table("matters") as batch:
        batch.drop_index("ix_matters_cassation_deadline")
        batch.drop_index("ix_matters_appeal_deadline")
        batch.drop_column("cassation_deadline")
        batch.drop_column("appeal_deadline")

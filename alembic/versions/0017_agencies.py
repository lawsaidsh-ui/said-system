"""add agencies

Revision ID: 0017_agencies
Revises: 0016_financial_date_quality
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_agencies"
down_revision: Union[str, None] = "0016_financial_date_quality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agency_number", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("matter_id", sa.Integer(), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("notary_office", sa.String(length=255), nullable=True),
        sa.Column("authorized_person", sa.String(length=255), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["matter_id"], ["matters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agency_number"),
    )
    op.create_index("ix_agencies_agency_number", "agencies", ["agency_number"])
    op.create_index("ix_agencies_client_id", "agencies", ["client_id"])
    op.create_index("ix_agencies_matter_id", "agencies", ["matter_id"])
    op.create_index("ix_agencies_expires_at", "agencies", ["expires_at"])
    op.create_index("ix_agencies_status", "agencies", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agencies_status", table_name="agencies")
    op.drop_index("ix_agencies_expires_at", table_name="agencies")
    op.drop_index("ix_agencies_matter_id", table_name="agencies")
    op.drop_index("ix_agencies_client_id", table_name="agencies")
    op.drop_index("ix_agencies_agency_number", table_name="agencies")
    op.drop_table("agencies")

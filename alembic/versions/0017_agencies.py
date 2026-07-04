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
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    if "agencies" not in table_names:
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

    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("agencies")}
    index_specs = {
        "ix_agencies_agency_number": ["agency_number"],
        "ix_agencies_client_id": ["client_id"],
        "ix_agencies_matter_id": ["matter_id"],
        "ix_agencies_expires_at": ["expires_at"],
        "ix_agencies_status": ["status"],
    }
    for index_name, columns in index_specs.items():
        if index_name not in indexes:
            op.create_index(index_name, "agencies", columns)


def downgrade() -> None:
    # Production safety: this migration may be stamped after the table was
    # created by an earlier deploy path, so downgrading must not drop data.
    pass

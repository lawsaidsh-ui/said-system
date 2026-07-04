"""ensure agencies table exists

Revision ID: 0018_agency
Revises: 0017_agencies
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018_agency"
down_revision: Union[str, None] = "0017_agencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_missing_indexes() -> None:
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


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "agencies" not in set(inspector.get_table_names()):
        op.create_table(
            "agencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agency_number", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column("matter_id", sa.Integer(), nullable=True),
            sa.Column("issued_at", sa.Date(), nullable=True),
            sa.Column("expires_at", sa.Date(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("notary_office", sa.String(length=255), nullable=True),
            sa.Column("authorized_person", sa.String(length=255), nullable=True),
            sa.Column("scope", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
            sa.ForeignKeyConstraint(["matter_id"], ["matters.id"]),
            sa.UniqueConstraint("agency_number"),
        )
    _create_missing_indexes()


def downgrade() -> None:
    # Production safety: never drop the agencies table or its data automatically.
    pass

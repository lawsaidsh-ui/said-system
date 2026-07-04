"""ensure agencies table and indexes exist (idempotent)

Revision ID: 0019_fix_agencies
Revises: 0018_agency
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0019_fix_agencies"
down_revision: Union[str, None] = "0018_agency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "agencies" not in inspector.get_table_names():
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

    existing_indexes = {
        idx["name"]
        for idx in sa.inspect(op.get_bind()).get_indexes("agencies")
    }
    index_specs = {
        "ix_agencies_agency_number": ["agency_number"],
        "ix_agencies_client_id": ["client_id"],
        "ix_agencies_matter_id": ["matter_id"],
        "ix_agencies_expires_at": ["expires_at"],
        "ix_agencies_status": ["status"],
    }
    for name, columns in index_specs.items():
        if name not in existing_indexes:
            op.create_index(name, "agencies", columns)


def downgrade() -> None:
    pass

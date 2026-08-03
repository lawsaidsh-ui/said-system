"""add soft delete timestamp to users

Revision ID: 0020_user_soft_delete
Revises: 0019_fix_agencies
Create Date: 2026-08-03
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020_user_soft_delete"
down_revision: Union[str, None] = "0019_fix_agencies"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "deleted_at" not in columns:
        op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_deleted_at" not in indexes:
        op.create_index("ix_users_deleted_at", "users", ["deleted_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("users")}
    if "ix_users_deleted_at" in indexes:
        op.drop_index("ix_users_deleted_at", table_name="users")
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "deleted_at" in columns:
        op.drop_column("users", "deleted_at")

"""add decision type to court sessions

Revision ID: 0021_session_decision_type
Revises: 0020_user_soft_delete
Create Date: 2026-08-03
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0021_session_decision_type"
down_revision: Union[str, None] = "0020_user_soft_delete"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "court_sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("court_sessions")}
    if "decision_type" not in columns:
        op.add_column("court_sessions", sa.Column("decision_type", sa.String(length=40), nullable=True))
    indexes = {index["name"] for index in inspector.get_indexes("court_sessions")}
    if "ix_court_sessions_decision_type" not in indexes:
        op.create_index("ix_court_sessions_decision_type", "court_sessions", ["decision_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "court_sessions" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("court_sessions")}
    if "ix_court_sessions_decision_type" in indexes:
        op.drop_index("ix_court_sessions_decision_type", table_name="court_sessions")
    columns = {column["name"] for column in inspector.get_columns("court_sessions")}
    if "decision_type" in columns:
        op.drop_column("court_sessions", "decision_type")

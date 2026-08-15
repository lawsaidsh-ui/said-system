"""fix PostgreSQL id defaults for court document tables

Revision ID: 0023_court_document_id_defaults
Revises: 0022_court_documents
Create Date: 2026-08-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0023_court_document_id_defaults"
down_revision: Union[str, None] = "0022_court_documents"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _ensure_id_default(table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return
    id_column = next((column for column in inspector.get_columns(table_name) if column["name"] == "id"), None)
    if not id_column or id_column.get("default") or id_column.get("identity"):
        return
    sequence_name = f"{table_name}_id_seq"
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} OWNED BY {table_name}.id"))
    op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN id SET DEFAULT nextval('{sequence_name}')"))
    op.execute(
        sa.text(
            f"""
            SELECT setval(
                '{sequence_name}',
                GREATEST(COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, 1),
                false
            )
            """
        )
    )


def upgrade() -> None:
    _ensure_id_default("court_document_templates")
    _ensure_id_default("generated_court_documents")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    for table_name in ["generated_court_documents", "court_document_templates"]:
        if table_name in inspector.get_table_names():
            op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN id DROP DEFAULT"))

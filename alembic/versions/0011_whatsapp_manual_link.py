"""whatsapp manual link

Revision ID: 0011_whatsapp_manual_link
Revises: 0010_matter_filing_deadlines
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_whatsapp_manual_link"
down_revision: Union[str, None] = "0010_matter_filing_deadlines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "whatsapp_templates" not in tables:
        op.create_table(
            "whatsapp_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("template_type", sa.String(length=80), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "whatsapp_logs" not in tables:
        op.create_table(
            "whatsapp_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id")),
            sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id")),
            sa.Column("template_id", sa.Integer(), sa.ForeignKey("whatsapp_templates.id")),
            sa.Column("template_type", sa.String(length=80)),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("phone_raw", sa.String(length=80)),
            sa.Column("phone_clean", sa.String(length=30)),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("source_type", sa.String(length=40)),
            sa.Column("source_id", sa.Integer()),
            sa.Column("status", sa.String(length=40), server_default="cancelled"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    inspector = sa.inspect(bind)
    template_indexes = {index["name"] for index in inspector.get_indexes("whatsapp_templates")}
    if "ix_whatsapp_templates_template_type" not in template_indexes:
        op.create_index("ix_whatsapp_templates_template_type", "whatsapp_templates", ["template_type"])

    log_indexes = {index["name"] for index in inspector.get_indexes("whatsapp_logs")}
    for name, columns in [
        ("ix_whatsapp_logs_client_id", ["client_id"]),
        ("ix_whatsapp_logs_matter_id", ["matter_id"]),
        ("ix_whatsapp_logs_template_id", ["template_id"]),
        ("ix_whatsapp_logs_template_type", ["template_type"]),
        ("ix_whatsapp_logs_phone_clean", ["phone_clean"]),
        ("ix_whatsapp_logs_employee_id", ["employee_id"]),
        ("ix_whatsapp_logs_source_type", ["source_type"]),
        ("ix_whatsapp_logs_source_id", ["source_id"]),
        ("ix_whatsapp_logs_status", ["status"]),
    ]:
        if name not in log_indexes:
            op.create_index(name, "whatsapp_logs", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "whatsapp_logs" in tables:
        op.drop_table("whatsapp_logs")
    if "whatsapp_templates" in tables:
        template_indexes = {index["name"] for index in inspector.get_indexes("whatsapp_templates")}
        if "ix_whatsapp_templates_template_type" in template_indexes:
            op.drop_index("ix_whatsapp_templates_template_type", table_name="whatsapp_templates")
        op.drop_table("whatsapp_templates")

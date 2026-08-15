"""add court document templates and generated letters

Revision ID: 0022_court_documents
Revises: 0021_session_decision_type
Create Date: 2026-08-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0022_court_documents"
down_revision: Union[str, None] = "0021_session_decision_type"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        additions = [
            ("job_title", sa.Column("job_title", sa.String(length=255), nullable=True)),
            ("signature_path", sa.Column("signature_path", sa.String(length=500), nullable=True)),
            ("can_issue_signed_letters", sa.Column("can_issue_signed_letters", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("can_use_office_stamp", sa.Column("can_use_office_stamp", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("can_update_own_signature", sa.Column("can_update_own_signature", sa.Boolean(), nullable=False, server_default=sa.false())),
        ]
        for column_name, column in additions:
            if column_name not in user_columns:
                op.add_column("users", column)

    if "court_document_templates" not in tables:
        op.create_table(
            "court_document_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=120), nullable=False),
            sa.Column("target_entity", sa.String(length=255), nullable=True),
            sa.Column("subject_template", sa.String(length=500), nullable=False),
            sa.Column("body_html", sa.Text(), nullable=False),
            sa.Column("variables_schema", sa.Text(), nullable=True),
            sa.Column("allowed_roles", sa.Text(), nullable=True),
            sa.Column("include_letterhead", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_signature", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("include_stamp", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        )
        op.create_index("ix_court_document_templates_name", "court_document_templates", ["name"])
        op.create_index("ix_court_document_templates_category", "court_document_templates", ["category"])
        op.create_index("ix_court_document_templates_target_entity", "court_document_templates", ["target_entity"])
        op.create_index("ix_court_document_templates_is_active", "court_document_templates", ["is_active"])
        op.create_index("ix_court_document_templates_created_by_id", "court_document_templates", ["created_by_id"])

    if "generated_court_documents" not in tables:
        op.create_table(
            "generated_court_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reference_number", sa.String(length=120), nullable=True),
            sa.Column("template_id", sa.Integer(), sa.ForeignKey("court_document_templates.id"), nullable=True),
            sa.Column("template_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=True),
            sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id"), nullable=True),
            sa.Column("court_name", sa.String(length=255), nullable=True),
            sa.Column("department_name", sa.String(length=255), nullable=True),
            sa.Column("subject", sa.String(length=500), nullable=False),
            sa.Column("values_json", sa.Text(), nullable=True),
            sa.Column("rendered_html_snapshot", sa.Text(), nullable=True),
            sa.Column("template_snapshot", sa.Text(), nullable=True),
            sa.Column("signature_snapshot_path", sa.String(length=500), nullable=True),
            sa.Column("letterhead_snapshot_path", sa.String(length=500), nullable=True),
            sa.Column("stamp_snapshot_path", sa.String(length=500), nullable=True),
            sa.Column("pdf_path", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("issued_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revocation_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        )
        op.create_index("ix_generated_court_documents_reference_number", "generated_court_documents", ["reference_number"], unique=True)
        op.create_index("ix_generated_court_documents_template_id", "generated_court_documents", ["template_id"])
        op.create_index("ix_generated_court_documents_client_id", "generated_court_documents", ["client_id"])
        op.create_index("ix_generated_court_documents_matter_id", "generated_court_documents", ["matter_id"])
        op.create_index("ix_generated_court_documents_court_name", "generated_court_documents", ["court_name"])
        op.create_index("ix_generated_court_documents_status", "generated_court_documents", ["status"])
        op.create_index("ix_generated_court_documents_issued_by_id", "generated_court_documents", ["issued_by_id"])
        op.create_index("ix_generated_court_documents_issued_at", "generated_court_documents", ["issued_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "generated_court_documents" in tables:
        op.drop_table("generated_court_documents")
    if "court_document_templates" in tables:
        op.drop_table("court_document_templates")
    if "users" in tables:
        for column_name in [
            "can_update_own_signature",
            "can_use_office_stamp",
            "can_issue_signed_letters",
            "signature_path",
            "job_title",
        ]:
            if _has_column(inspector, "users", column_name):
                op.drop_column("users", column_name)

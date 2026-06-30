"""add task automation fields and notifications

Revision ID: 0009_tasks_automation
Revises: 0008_oman_court_defaults
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_tasks_automation"
down_revision = "0008_oman_court_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}

    task_additions = [
        ("task_type", sa.Column("task_type", sa.String(length=60), nullable=False, server_default="internal_reminder")),
        ("invoice_id", sa.Column("invoice_id", sa.Integer(), nullable=True)),
        ("assigned_role", sa.Column("assigned_role", sa.String(length=40), nullable=True)),
        ("notes", sa.Column("notes", sa.Text(), nullable=True)),
        ("source", sa.Column("source", sa.String(length=40), nullable=False, server_default="manual")),
        ("source_key", sa.Column("source_key", sa.String(length=180), nullable=True)),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)),
    ]
    for name, column in task_additions:
        if name not in task_columns:
            op.add_column("tasks", column)

    task_index_additions = [
        ("ix_tasks_task_type", ["task_type"], False),
        ("ix_tasks_invoice_id", ["invoice_id"], False),
        ("ix_tasks_assigned_role", ["assigned_role"], False),
        ("ix_tasks_source", ["source"], False),
        ("ix_tasks_source_key", ["source_key"], True),
    ]
    for name, columns, unique in task_index_additions:
        if name not in task_indexes:
            op.create_index(name, "tasks", columns, unique=unique)

    task_foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("tasks")}
    if bind.dialect.name != "sqlite" and "fk_tasks_invoice_id_invoices" not in task_foreign_keys:
        op.create_foreign_key("fk_tasks_invoice_id_invoices", "tasks", "invoices", ["invoice_id"], ["id"])

    tables = set(inspector.get_table_names())
    if "notifications" not in tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("notification_type", sa.String(length=60), nullable=False),
            sa.Column("channel", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("source_key", sa.String(length=180), nullable=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        inspector = sa.inspect(bind)

    notification_indexes = {index["name"] for index in inspector.get_indexes("notifications")}
    notification_index_additions = [
        ("ix_notifications_user_id", ["user_id"], False),
        ("ix_notifications_task_id", ["task_id"], False),
        ("ix_notifications_notification_type", ["notification_type"], False),
        ("ix_notifications_status", ["status"], False),
        ("ix_notifications_source_key", ["source_key"], True),
    ]
    for name, columns, unique in notification_index_additions:
        if name not in notification_indexes:
            op.create_index(name, "notifications", columns, unique=unique)


def downgrade() -> None:
    op.drop_index("ix_notifications_source_key", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_notification_type", table_name="notifications")
    op.drop_index("ix_notifications_task_id", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("fk_tasks_invoice_id_invoices", type_="foreignkey")
        batch.drop_index("ix_tasks_source_key")
        batch.drop_index("ix_tasks_source")
        batch.drop_index("ix_tasks_assigned_role")
        batch.drop_index("ix_tasks_invoice_id")
        batch.drop_index("ix_tasks_task_type")
        batch.drop_column("completed_at")
        batch.drop_column("source_key")
        batch.drop_column("source")
        batch.drop_column("notes")
        batch.drop_column("assigned_role")
        batch.drop_column("invoice_id")
        batch.drop_column("task_type")

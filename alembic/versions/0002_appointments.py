"""add appointments

Revision ID: 0002_appointments
Revises: 0001_initial
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_appointments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("appointment_date", sa.Date(), nullable=False),
        sa.Column("appointment_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_date", "appointment_time", name="uq_appointment_slot"),
    )
    op.create_index(op.f("ix_appointments_appointment_date"), "appointments", ["appointment_date"], unique=False)
    op.create_index(op.f("ix_appointments_appointment_time"), "appointments", ["appointment_time"], unique=False)
    op.create_index(op.f("ix_appointments_phone"), "appointments", ["phone"], unique=False)
    op.create_index(op.f("ix_appointments_status"), "appointments", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_appointments_status"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_phone"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_appointment_time"), table_name="appointments")
    op.drop_index(op.f("ix_appointments_appointment_date"), table_name="appointments")
    op.drop_table("appointments")

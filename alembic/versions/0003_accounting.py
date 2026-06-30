"""add accounting system

Revision ID: 0003_accounting
Revises: 0002_appointments
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa

from app.database import Base
from app import models  # noqa: F401


revision = "0003_accounting"
down_revision = "0002_appointments"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())
    return
    op.create_table("case_fees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id"), nullable=False),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("fee_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_plan", sa.String(40), nullable=False),
        sa.Column("advance_payment", sa.Numeric(12, 2), nullable=False),
        sa.Column("monthly_installment", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table("receipt_vouchers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_number", sa.String(120), nullable=False, unique=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id"), nullable=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("received_at", sa.Date(), nullable=False),
        sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reference_no", sa.String(120), nullable=True),
        sa.Column("attachment_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table("payment_vouchers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("voucher_number", sa.String(120), nullable=False, unique=True),
        sa.Column("expense_type", sa.String(120), nullable=False),
        sa.Column("beneficiary", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("attachment_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approval_status", sa.String(40), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table("expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id"), nullable=True),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("attachment_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table("financial_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(80), nullable=False),
        sa.Column("opening_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table("chart_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(80), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("chart_accounts.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
    )
    op.create_table("account_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("to_account_id", sa.Integer(), sa.ForeignKey("financial_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table("journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_number", sa.String(120), nullable=False, unique=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("debit_account_id", sa.Integer(), sa.ForeignKey("chart_accounts.id"), nullable=False),
        sa.Column("credit_account_id", sa.Integer(), sa.ForeignKey("chart_accounts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("attachment_url", sa.String(500), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table("salary_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("salary_month", sa.String(7), nullable=False),
        sa.Column("base_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("allowances", sa.Numeric(12, 2), nullable=False),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=False),
        sa.Column("advances", sa.Numeric(12, 2), nullable=False),
        sa.Column("net_salary", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("payment_voucher_id", sa.Integer(), sa.ForeignKey("payment_vouchers.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table("installments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("matter_id", sa.Integer(), sa.ForeignKey("matters.id"), nullable=True),
        sa.Column("case_fee_id", sa.Integer(), sa.ForeignKey("case_fees.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
    )


def downgrade() -> None:
    for table in [
        "installments", "salary_records", "journal_entries", "account_transfers", "chart_accounts",
        "financial_accounts", "expenses", "payment_vouchers", "receipt_vouchers", "case_fees",
    ]:
        op.drop_table(table)

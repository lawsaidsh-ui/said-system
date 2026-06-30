"""add owner financial settings

Revision ID: 0005_owner_financial_settings
Revises: 0004_success_fee_percentage
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_owner_financial_settings"
down_revision = "0004_success_fee_percentage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "owner_financial_settings" in inspector.get_table_names():
        return
    op.create_table(
        "owner_financial_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("monthly_fixed_expenses", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("monthly_revenue_target", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("monthly_profit_target", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("default_profit_margin", sa.Numeric(5, 2), nullable=False, server_default="70"),
        sa.Column("collection_warning_threshold", sa.Numeric(5, 2), nullable=False, server_default="75"),
        sa.Column("expense_warning_threshold", sa.Numeric(5, 2), nullable=False, server_default="15"),
        sa.Column("expense_categories_json", sa.Text(), nullable=True),
        sa.Column("service_categories_json", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "owner_financial_settings" in inspector.get_table_names():
        op.drop_table("owner_financial_settings")

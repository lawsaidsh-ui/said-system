"""link payment vouchers to clients and matters

Revision ID: 0012_payment_voucher_client_matter
Revises: 0011_whatsapp_manual_link
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_payment_voucher_client_matter"
down_revision: Union[str, None] = "0011_whatsapp_manual_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("payment_vouchers")}
    indexes = {index["name"] for index in inspector.get_indexes("payment_vouchers")}

    if "client_id" not in columns:
        op.add_column("payment_vouchers", sa.Column("client_id", sa.Integer(), nullable=True))
    if "matter_id" not in columns:
        op.add_column("payment_vouchers", sa.Column("matter_id", sa.Integer(), nullable=True))
    if "ix_payment_vouchers_client_id" not in indexes:
        op.create_index("ix_payment_vouchers_client_id", "payment_vouchers", ["client_id"])
    if "ix_payment_vouchers_matter_id" not in indexes:
        op.create_index("ix_payment_vouchers_matter_id", "payment_vouchers", ["matter_id"])

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("payment_vouchers")}
    if bind.dialect.name != "sqlite":
        if "fk_payment_vouchers_client_id_clients" not in foreign_keys:
            op.create_foreign_key("fk_payment_vouchers_client_id_clients", "payment_vouchers", "clients", ["client_id"], ["id"])
        if "fk_payment_vouchers_matter_id_matters" not in foreign_keys:
            op.create_foreign_key("fk_payment_vouchers_matter_id_matters", "payment_vouchers", "matters", ["matter_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("payment_vouchers")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("payment_vouchers")}

    if bind.dialect.name != "sqlite":
        if "fk_payment_vouchers_matter_id_matters" in foreign_keys:
            op.drop_constraint("fk_payment_vouchers_matter_id_matters", "payment_vouchers", type_="foreignkey")
        if "fk_payment_vouchers_client_id_clients" in foreign_keys:
            op.drop_constraint("fk_payment_vouchers_client_id_clients", "payment_vouchers", type_="foreignkey")
    if "ix_payment_vouchers_matter_id" in indexes:
        op.drop_index("ix_payment_vouchers_matter_id", table_name="payment_vouchers")
    if "ix_payment_vouchers_client_id" in indexes:
        op.drop_index("ix_payment_vouchers_client_id", table_name="payment_vouchers")
    with op.batch_alter_table("payment_vouchers") as batch:
        batch.drop_column("matter_id")
        batch.drop_column("client_id")

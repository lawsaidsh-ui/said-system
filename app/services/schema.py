from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


DATE_QUALITY_TABLES = {
    "payments": "payment_date",
    "receipt_vouchers": "received_at",
    "expenses": "expense_date",
    "payment_vouchers": "paid_at",
    "journal_entries": "entry_date",
}


def _ensure_date_quality_columns(engine: Engine, table_names: set[str]) -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table_name in DATE_QUALITY_TABLES:
            if table_name not in table_names:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "date_status" not in columns:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN date_status VARCHAR(20) NOT NULL DEFAULT 'confirmed'"))
            if "date_note" not in columns:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN date_note TEXT"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_date_status ON {table_name} (date_status)"))


def ensure_runtime_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS whatsapp_templates (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    template_type VARCHAR(80) NOT NULL,
                    body TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_templates_template_type ON whatsapp_templates (template_type)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS whatsapp_logs (
                    id INTEGER PRIMARY KEY,
                    client_id INTEGER,
                    matter_id INTEGER,
                    template_id INTEGER,
                    template_type VARCHAR(80),
                    message TEXT NOT NULL,
                    phone_raw VARCHAR(80),
                    phone_clean VARCHAR(30),
                    employee_id INTEGER,
                    source_type VARCHAR(40),
                    source_id INTEGER,
                    status VARCHAR(40) DEFAULT 'تم الإلغاء',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_client_id ON whatsapp_logs (client_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_matter_id ON whatsapp_logs (matter_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_template_id ON whatsapp_logs (template_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_template_type ON whatsapp_logs (template_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_phone_clean ON whatsapp_logs (phone_clean)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_employee_id ON whatsapp_logs (employee_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_source_type ON whatsapp_logs (source_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_source_id ON whatsapp_logs (source_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_whatsapp_logs_status ON whatsapp_logs (status)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fixed_monthly_expenses (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    category VARCHAR(120) NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                    due_day INTEGER NOT NULL DEFAULT 1,
                    payment_method VARCHAR(40),
                    vendor_name VARCHAR(255),
                    notes TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_monthly_expenses_title ON fixed_monthly_expenses (title)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_monthly_expenses_category ON fixed_monthly_expenses (category)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fixed_monthly_expenses_vendor_name ON fixed_monthly_expenses (vendor_name)"))
    _ensure_date_quality_columns(engine, table_names)

    if "tasks" not in table_names:
        return
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    additions = {
        "task_type": "ALTER TABLE tasks ADD COLUMN task_type VARCHAR(60) NOT NULL DEFAULT 'internal_reminder'",
        "invoice_id": "ALTER TABLE tasks ADD COLUMN invoice_id INTEGER",
        "assigned_role": "ALTER TABLE tasks ADD COLUMN assigned_role VARCHAR(40)",
        "notes": "ALTER TABLE tasks ADD COLUMN notes TEXT",
        "source": "ALTER TABLE tasks ADD COLUMN source VARCHAR(40) NOT NULL DEFAULT 'manual'",
        "source_key": "ALTER TABLE tasks ADD COLUMN source_key VARCHAR(180)",
        "completed_at": "ALTER TABLE tasks ADD COLUMN completed_at DATETIME",
    }
    with engine.begin() as conn:
        for column_name, sql in additions.items():
            if column_name not in task_columns:
                conn.execute(text(sql))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_task_type ON tasks (task_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_invoice_id ON tasks (invoice_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_assigned_role ON tasks (assigned_role)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_source ON tasks (source)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_source_key ON tasks (source_key)"))
    if "matters" not in table_names:
        return
    matter_columns = {column["name"] for column in inspector.get_columns("matters")}
    matter_additions = {
        "appeal_deadline": "ALTER TABLE matters ADD COLUMN appeal_deadline DATE",
        "cassation_deadline": "ALTER TABLE matters ADD COLUMN cassation_deadline DATE",
    }
    with engine.begin() as conn:
        for column_name, sql in matter_additions.items():
            if column_name not in matter_columns:
                conn.execute(text(sql))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_matters_appeal_deadline ON matters (appeal_deadline)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_matters_cassation_deadline ON matters (cassation_deadline)"))
    if "payment_vouchers" not in table_names:
        return
    payment_voucher_columns = {column["name"] for column in inspector.get_columns("payment_vouchers")}
    payment_voucher_additions = {
        "client_id": "ALTER TABLE payment_vouchers ADD COLUMN client_id INTEGER",
        "matter_id": "ALTER TABLE payment_vouchers ADD COLUMN matter_id INTEGER",
    }
    with engine.begin() as conn:
        for column_name, sql in payment_voucher_additions.items():
            if column_name not in payment_voucher_columns:
                conn.execute(text(sql))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_vouchers_client_id ON payment_vouchers (client_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_vouchers_matter_id ON payment_vouchers (matter_id)"))
    if "case_fees" not in table_names:
        return
    case_fee_columns = {column["name"] for column in inspector.get_columns("case_fees")}
    case_fee_additions = {
        "group_key": "ALTER TABLE case_fees ADD COLUMN group_key VARCHAR(80)",
        "group_total_amount": "ALTER TABLE case_fees ADD COLUMN group_total_amount NUMERIC(12, 2)",
        "is_group_primary": "ALTER TABLE case_fees ADD COLUMN is_group_primary BOOLEAN NOT NULL DEFAULT 1",
    }
    with engine.begin() as conn:
        for column_name, sql in case_fee_additions.items():
            if column_name not in case_fee_columns:
                conn.execute(text(sql))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_case_fees_group_key ON case_fees (group_key)"))
    if "receipt_vouchers" not in table_names:
        return
    receipt_columns = {column["name"] for column in inspector.get_columns("receipt_vouchers")}
    receipt_additions = {
        "case_fee_id": "ALTER TABLE receipt_vouchers ADD COLUMN case_fee_id INTEGER",
        "receipt_type": "ALTER TABLE receipt_vouchers ADD COLUMN receipt_type VARCHAR(40) NOT NULL DEFAULT 'case_fee'",
    }
    with engine.begin() as conn:
        for column_name, sql in receipt_additions.items():
            if column_name not in receipt_columns:
                conn.execute(text(sql))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_receipt_vouchers_case_fee_id ON receipt_vouchers (case_fee_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_receipt_vouchers_receipt_type ON receipt_vouchers (receipt_type)"))

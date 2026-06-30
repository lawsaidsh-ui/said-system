from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assigned_matters: Mapped[list["Matter"]] = relationship(
        back_populates="assigned_lawyer", foreign_keys="Matter.assigned_lawyer_id"
    )
    assigned_tasks: Mapped[list["Task"]] = relationship(back_populates="assigned_to", foreign_keys="Task.assigned_to_id")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", foreign_keys="Notification.user_id")
    whatsapp_logs: Mapped[list["WhatsAppLog"]] = relationship(back_populates="employee", foreign_keys="WhatsAppLog.employee_id")


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    civil_id: Mapped[str | None] = mapped_column(String(80), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    client_type: Mapped[str] = mapped_column(String(30), nullable=False, default="individual")
    company_name: Mapped[str | None] = mapped_column(String(255))
    commercial_registration: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    matters: Mapped[list["Matter"]] = relationship(back_populates="client")
    documents: Mapped[list["Document"]] = relationship(back_populates="client")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client")
    consultations: Mapped[list["Consultation"]] = relationship(back_populates="client")
    whatsapp_logs: Mapped[list["WhatsAppLog"]] = relationship(back_populates="client")


class Matter(TimestampMixin, Base):
    __tablename__ = "matters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_number: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    ministry_case_number: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    assigned_lawyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    case_type: Mapped[str | None] = mapped_column(String(120), index=True)
    court_name: Mapped[str | None] = mapped_column(String(255), index=True)
    court_level: Mapped[str | None] = mapped_column(String(120))
    opponent_name: Mapped[str | None] = mapped_column(String(255))
    opponent_phone: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40), index=True, default="new")
    priority: Mapped[str] = mapped_column(String(40), index=True, default="medium")
    description: Mapped[str | None] = mapped_column(Text)
    claim_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    opened_at: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    appeal_deadline: Mapped[date | None] = mapped_column(Date, index=True)
    cassation_deadline: Mapped[date | None] = mapped_column(Date, index=True)

    client: Mapped[Client] = relationship(back_populates="matters")
    assigned_lawyer: Mapped[User | None] = relationship(back_populates="assigned_matters", foreign_keys=[assigned_lawyer_id])
    sessions: Mapped[list["CourtSession"]] = relationship(back_populates="matter")
    tasks: Mapped[list["Task"]] = relationship(back_populates="matter")
    documents: Mapped[list["Document"]] = relationship(back_populates="matter")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="matter")
    whatsapp_logs: Mapped[list["WhatsAppLog"]] = relationship(back_populates="matter")


class WhatsAppTemplate(TimestampMixin, Base):
    __tablename__ = "whatsapp_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    logs: Mapped[list["WhatsAppLog"]] = relationship(back_populates="template")


class WhatsAppLog(Base):
    __tablename__ = "whatsapp_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("whatsapp_templates.id"), index=True)
    template_type: Mapped[str | None] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    phone_raw: Mapped[str | None] = mapped_column(String(80))
    phone_clean: Mapped[str | None] = mapped_column(String(30), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), index=True)
    source_id: Mapped[int | None] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default="cancelled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client | None] = relationship(back_populates="whatsapp_logs")
    matter: Mapped[Matter | None] = relationship(back_populates="whatsapp_logs")
    template: Mapped[WhatsAppTemplate | None] = relationship(back_populates="logs")
    employee: Mapped[User | None] = relationship(back_populates="whatsapp_logs", foreign_keys=[employee_id])


class CourtSession(TimestampMixin, Base):
    __tablename__ = "court_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    matter_id: Mapped[int] = mapped_column(ForeignKey("matters.id"), index=True, nullable=False)
    session_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    session_time: Mapped[time | None] = mapped_column(Time)
    court_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hall_number: Mapped[str | None] = mapped_column(String(80))
    judge_name: Mapped[str | None] = mapped_column(String(255))
    session_status: Mapped[str] = mapped_column(String(40), index=True, default="scheduled")
    decision_summary: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    next_session_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    matter: Mapped[Matter] = relationship(back_populates="sessions")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(60), index=True, default="internal_reminder")
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_role: Mapped[str | None] = mapped_column(String(40), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    priority: Mapped[str] = mapped_column(String(40), index=True, default="medium")
    status: Mapped[str] = mapped_column(String(40), index=True, default="new")
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), index=True, default="manual")
    source_key: Mapped[str | None] = mapped_column(String(180), unique=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    matter: Mapped[Matter | None] = relationship(back_populates="tasks")
    client: Mapped[Client | None] = relationship()
    invoice: Mapped["Invoice | None"] = relationship(back_populates="tasks")
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id], back_populates="assigned_tasks")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    notifications: Mapped[list["Notification"]] = relationship(back_populates="task")


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    notification_type: Mapped[str] = mapped_column(String(60), index=True, default="task_created")
    channel: Mapped[str] = mapped_column(String(40), default="in_app")
    status: Mapped[str] = mapped_column(String(40), index=True, default="new")
    source_key: Mapped[str | None] = mapped_column(String(180), unique=True, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship(back_populates="notifications", foreign_keys=[user_id])
    task: Mapped[Task | None] = relationship(back_populates="notifications")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    document_type: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    matter: Mapped[Matter | None] = relationship(back_populates="documents")
    client: Mapped[Client | None] = relationship(back_populates="documents")
    uploaded_by: Mapped[User | None] = relationship()


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(40), index=True, default="unpaid")
    notes: Mapped[str | None] = mapped_column(Text)

    client: Mapped[Client] = relationship(back_populates="invoices")
    matter: Mapped[Matter | None] = relationship(back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")
    tasks: Mapped[list[Task]] = relationship(back_populates="invoice")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_status: Mapped[str] = mapped_column(String(20), index=True, default="confirmed", nullable=False)
    date_note: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(40), default="cash")
    reference_no: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="payments")


class Consultation(TimestampMixin, Base):
    __tablename__ = "consultations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requester_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    requester_email: Mapped[str | None] = mapped_column(String(255))
    consultation_type: Mapped[str | None] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True, default="new")
    assigned_lawyer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    consultation_date: Mapped[date | None] = mapped_column(Date)
    fee_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    client: Mapped[Client | None] = relationship(back_populates="consultations")
    assigned_lawyer: Mapped[User | None] = relationship()


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("appointment_date", "appointment_time", name="uq_appointment_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    appointment_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    appointment_time: Mapped[time] = mapped_column(Time, index=True, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    topic: Mapped[str | None] = mapped_column(String(255))
    case_type: Mapped[str | None] = mapped_column(String(120))
    litigation_degree: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True, default="pending")
    source: Mapped[str] = mapped_column(String(40), default="public")


class OfficeSetting(Base):
    __tablename__ = "office_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OwnerFinancialSetting(Base):
    __tablename__ = "owner_financial_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monthly_fixed_expenses: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    monthly_revenue_target: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    monthly_profit_target: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    default_profit_margin: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=70)
    collection_warning_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=75)
    expense_warning_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=15)
    expense_categories_json: Mapped[str | None] = mapped_column(Text)
    service_categories_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    old_value_json: Mapped[str | None] = mapped_column(Text)
    new_value_json: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()


class CaseFee(TimestampMixin, Base):
    __tablename__ = "case_fees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    matter_id: Mapped[int] = mapped_column(ForeignKey("matters.id"), index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    success_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    won_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    payment_plan: Mapped[str] = mapped_column(String(40), default="one_time")
    group_key: Mapped[str | None] = mapped_column(String(80), index=True)
    group_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_group_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    advance_payment: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    monthly_installment: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), index=True, default="partial")
    notes: Mapped[str | None] = mapped_column(Text)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    matter: Mapped[Matter] = relationship()
    client: Mapped[Client] = relationship()


class ReceiptVoucher(Base):
    __tablename__ = "receipt_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    case_fee_id: Mapped[int | None] = mapped_column(ForeignKey("case_fees.id"), index=True)
    receipt_type: Mapped[str] = mapped_column(String(40), index=True, default="case_fee")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), default="cash")
    received_at: Mapped[date] = mapped_column(Date, nullable=False)
    date_status: Mapped[str] = mapped_column(String(20), index=True, default="confirmed", nullable=False)
    date_note: Mapped[str | None] = mapped_column(Text)
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    reference_no: Mapped[str | None] = mapped_column(String(120))
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client] = relationship()
    matter: Mapped[Matter | None] = relationship()
    invoice: Mapped[Invoice | None] = relationship()
    case_fee: Mapped[CaseFee | None] = relationship()
    received_by: Mapped[User | None] = relationship()


class PaymentVoucher(Base):
    __tablename__ = "payment_vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_number: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    expense_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    beneficiary: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(40), default="cash")
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)
    date_status: Mapped[str] = mapped_column(String(20), index=True, default="confirmed", nullable=False)
    date_note: Mapped[str | None] = mapped_column(Text)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    approval_status: Mapped[str] = mapped_column(String(40), default="not_required")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[Client | None] = relationship()
    matter: Mapped[Matter | None] = relationship()
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    date_status: Mapped[str] = mapped_column(String(20), index=True, default="confirmed", nullable=False)
    date_note: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str] = mapped_column(String(40), default="cash")
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    added_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active")
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    matter: Mapped[Matter | None] = relationship()
    added_by: Mapped[User | None] = relationship()


class FixedMonthlyExpense(TimestampMixin, Base):
    __tablename__ = "fixed_monthly_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payment_method: Mapped[str] = mapped_column(String(40), default="cash")
    vendor_name: Mapped[str | None] = mapped_column(String(255), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SalaryRecord(TimestampMixin, Base):
    __tablename__ = "salary_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    salary_month: Mapped[str] = mapped_column(String(7), index=True, nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    advances: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), index=True, default="unpaid")
    payment_voucher_id: Mapped[int | None] = mapped_column(ForeignKey("payment_vouchers.id"), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    payment_voucher: Mapped[PaymentVoucher | None] = relationship()


class Installment(TimestampMixin, Base):
    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    matter_id: Mapped[int | None] = mapped_column(ForeignKey("matters.id"), index=True)
    case_fee_id: Mapped[int | None] = mapped_column(ForeignKey("case_fees.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), index=True, default="pending")
    notes: Mapped[str | None] = mapped_column(Text)

    client: Mapped[Client] = relationship()
    matter: Mapped[Matter | None] = relationship()
    case_fee: Mapped[CaseFee | None] = relationship()


class FinancialAccount(TimestampMixin, Base):
    __tablename__ = "financial_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class AccountTransfer(Base):
    __tablename__ = "account_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), index=True, nullable=False)
    to_account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    from_account: Mapped[FinancialAccount] = relationship(foreign_keys=[from_account_id])
    to_account: Mapped[FinancialAccount] = relationship(foreign_keys=[to_account_id])
    created_by: Mapped[User | None] = relationship()


class ChartAccount(TimestampMixin, Base):
    __tablename__ = "chart_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chart_accounts.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class JournalEntry(TimestampMixin, Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_number: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    date_status: Mapped[str] = mapped_column(String(20), index=True, default="confirmed", nullable=False)
    date_note: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    debit_account_id: Mapped[int] = mapped_column(ForeignKey("chart_accounts.id"), index=True, nullable=False)
    credit_account_id: Mapped[int] = mapped_column(ForeignKey("chart_accounts.id"), index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, default="posted")
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    debit_account: Mapped[ChartAccount] = relationship(foreign_keys=[debit_account_id])
    credit_account: Mapped[ChartAccount] = relationship(foreign_keys=[credit_account_id])
    created_by: Mapped[User | None] = relationship()

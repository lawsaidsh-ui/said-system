from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    password: str
    role: str


class ClientCreate(BaseModel):
    full_name: str
    phone: str | None = None
    email: EmailStr | None = None
    civil_id: str | None = None
    client_type: str = "individual"


class MatterCreate(BaseModel):
    case_number: str | None = None
    ministry_case_number: str | None = None
    title: str
    client_id: int
    assigned_lawyer_id: int | None = None
    status: str = "new"
    priority: str = "medium"


class InvoiceCreate(BaseModel):
    invoice_number: str
    client_id: int
    matter_id: int | None = None
    issue_date: date
    due_date: date | None = None
    subtotal: Decimal
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")

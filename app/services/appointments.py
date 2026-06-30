from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Appointment

APPOINTMENT_START = time(15, 0)
APPOINTMENT_END = time(19, 0)
APPOINTMENT_DURATION_MINUTES = 30


def appointment_slots() -> list[time]:
    slots: list[time] = []
    current = datetime.combine(date.today(), APPOINTMENT_START)
    end = datetime.combine(date.today(), APPOINTMENT_END)
    step = timedelta(minutes=APPOINTMENT_DURATION_MINUTES)
    while current + step <= end:
        slots.append(current.time())
        current += step
    return slots


def parse_slot(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


def is_valid_slot(slot: time) -> bool:
    return slot in appointment_slots()


def booked_slots(db: Session, appointment_date: date) -> set[time]:
    return set(
        db.scalars(
            select(Appointment.appointment_time).where(
                Appointment.appointment_date == appointment_date,
                Appointment.status != "cancelled",
            )
        ).all()
    )


def available_slots(db: Session, appointment_date: date) -> list[time]:
    booked = booked_slots(db, appointment_date)
    return [slot for slot in appointment_slots() if slot not in booked]


CASE_TYPES = [
    "مدنية",
    "تجارية",
    "جزائية",
    "أحوال شخصية",
    "عمالية",
    "عقارية",
    "إدارية",
    "استثمار وتجارة",
    "تنفيذ",
    "تركات",
    "أخرى",
]

LITIGATION_DEGREES = [
    "لم تبدأ القضية بعد",
    "ابتدائي",
    "استئناف",
    "المحكمة العليا",
    "تنفيذ",
    "استشارة فقط",
]


def create_appointment(
    db: Session,
    *,
    client_name: str,
    phone: str,
    email: str | None,
    appointment_date: date,
    appointment_time: time,
    topic: str | None,
    case_type: str | None,
    litigation_degree: str | None,
    message: str | None,
) -> Appointment:
    if appointment_date < date.today():
        raise ValueError("لا يمكن حجز موعد في تاريخ سابق.")
    if not is_valid_slot(appointment_time):
        raise ValueError("وقت الموعد يجب أن يكون بين 3:00 و7:00 ومدة الموعد 30 دقيقة.")
    if appointment_time in booked_slots(db, appointment_date):
        raise ValueError("هذا الموعد محجوز بالفعل. اختر وقتاً آخر.")
    appointment = Appointment(
        client_name=client_name,
        phone=phone,
        email=email,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        duration_minutes=APPOINTMENT_DURATION_MINUTES,
        topic=topic,
        case_type=case_type,
        litigation_degree=litigation_degree,
        message=message,
        status="pending",
        source="public",
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("هذا الموعد محجوز بالفعل. اختر وقتاً آخر.") from exc
    db.refresh(appointment)
    return appointment

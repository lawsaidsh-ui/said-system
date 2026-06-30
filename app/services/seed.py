from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CaseFee, Client, Consultation, CourtSession, Expense, FixedMonthlyExpense, Installment, Invoice, Matter, OfficeSetting, Payment, Task, User
from app.services.audit import log_action
from app.services.accounting import seed_accounting_defaults
from app.services.security import hash_password


def ensure_office_setting(db: Session, *, key: str, value: str, description: str) -> None:
    setting = db.scalar(select(OfficeSetting).where(OfficeSetting.key == key))
    if not setting:
        db.add(OfficeSetting(key=key, value=value, description=description))
        return
    if not setting.value or setting.value in {"0500000000", "info@saeed-law.test", "دبي، الإمارات العربية المتحدة"}:
        setting.value = value
    setting.description = setting.description or description


def ensure_demo_user(db: Session, *, full_name: str, email: str, phone: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(
        full_name=full_name,
        email=email,
        phone=phone,
        password_hash=hash_password("Admin12345"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def seed_database(db: Session) -> None:
    users_count = db.scalar(select(func.count(User.id))) or 0
    if users_count:
        active_admin = db.scalar(select(User).where(User.role == "admin", User.is_active.is_(True)).limit(1))
        if not active_admin:
            recovery_admin = db.scalar(select(User).where(User.email == "admin@saeed-law.test"))
            if recovery_admin:
                recovery_admin.full_name = recovery_admin.full_name or "مدير النظام"
                recovery_admin.role = "admin"
                recovery_admin.is_active = True
                recovery_admin.password_hash = hash_password("Admin12345")
            else:
                ensure_demo_user(
                    db,
                    full_name="مدير النظام",
                    email="admin@saeed-law.test",
                    phone="0500000000",
                    role="admin",
                )
        ensure_office_setting(db, key="office_name", value="مكتب سعيد الشبيبي للمحاماة", description="اسم المكتب")
        ensure_office_setting(db, key="phone", value="+968 0000 0000", description="رقم الهاتف")
        ensure_office_setting(db, key="email", value="info@saeed-law.om", description="البريد الإلكتروني")
        ensure_office_setting(db, key="address", value="مسقط، سلطنة عمان", description="العنوان")
        ensure_office_setting(db, key="invoice_footer", value="شكراً لثقتكم بمكتب سعيد الشبيبي للمحاماة.", description="نص أسفل الفاتورة")
        db.commit()
        seed_accounting_defaults(db)
        seed_accounting_samples(db)
        seed_fixed_monthly_expenses(db)
        return

    admin = User(
        full_name="سعيد الشبيبي",
        email="admin@saeed-law.test",
        phone="0500000000",
        password_hash=hash_password("Admin12345"),
        role="admin",
        is_active=True,
    )
    lawyer = User(
        full_name="محامي تجريبي",
        email="lawyer@saeed-law.test",
        phone="0501111111",
        password_hash=hash_password("Admin12345"),
        role="lawyer",
        is_active=True,
    )
    secretary = User(
        full_name="سكرتير تجريبي",
        email="secretary@saeed-law.test",
        phone="0502222222",
        password_hash=hash_password("Admin12345"),
        role="secretary",
        is_active=True,
    )
    accountant = User(
        full_name="محاسب تجريبي",
        email="accountant@saeed-law.test",
        phone="0503333333",
        password_hash=hash_password("Admin12345"),
        role="accountant",
        is_active=True,
    )
    viewer = User(
        full_name="مشاهد تجريبي",
        email="viewer@saeed-law.test",
        phone="0504444444",
        password_hash=hash_password("Admin12345"),
        role="viewer",
        is_active=True,
    )
    data_entry = User(
        full_name="مدخل بيانات تجريبي",
        email="data-entry@saeed-law.test",
        phone="0505555555",
        password_hash=hash_password("Admin12345"),
        role="data_entry",
        is_active=True,
    )
    db.add_all([admin, lawyer, secretary, accountant, data_entry, viewer])
    db.flush()

    clients = [
        Client(full_name="أحمد سالم", phone="91234567", email="ahmed@example.test", civil_id="1980000001", client_type="individual", notes="عميل تجريبي"),
        Client(full_name="شركة النور للتجارة", phone="92345678", email="info@alnoor.test", client_type="company", company_name="شركة النور للتجارة", commercial_registration="1001001"),
        Client(full_name="مريم خالد", phone="95512345", email="mariam@example.test", civil_id="1990000002", client_type="individual"),
        Client(full_name="خالد عبدالله", phone="95212345", email="khalid@example.test", civil_id="1975000003", client_type="individual"),
        Client(full_name="شركة الخليج العقارية", phone="71112233", email="legal@gulf-re.test", client_type="company", company_name="شركة الخليج العقارية", commercial_registration="2002002"),
    ]
    db.add_all(clients)
    db.flush()

    statuses = ["new", "open", "in_progress", "waiting", "court_session", "closed", "archived", "open"]
    priorities = ["medium", "high", "urgent", "low", "medium", "high", "low", "urgent"]
    matters = []
    for idx in range(8):
        matters.append(
            Matter(
                case_number=f"OFF-2026-{idx + 1:04d}",
                ministry_case_number=f"قضاء-2026-{idx + 1:05d}" if idx % 2 == 0 else None,
                title=f"قضية تجريبية رقم {idx + 1}",
                client_id=clients[idx % len(clients)].id,
                assigned_lawyer_id=lawyer.id,
                case_type=["مدني", "تجاري", "عمالي", "أحوال شخصية", "جزائي", "عقاري"][idx % 6],
                court_name=["المحكمة الابتدائية بمسقط", "محكمة الاستئناف بمسقط", "المحكمة الابتدائية بالسيب", "محكمة الاستئناف بنزوى", "المحكمة الابتدائية بصحار"][idx % 5],
                court_level=["ابتدائي", "استئناف", "عليا", "تنفيذ"][idx % 4],
                opponent_name=f"الخصم {idx + 1}",
                status=statuses[idx],
                priority=priorities[idx],
                description="وصف مختصر للقضية والملاحظات القانونية الأولية.",
                claim_amount=Decimal("15000.00") + idx * Decimal("2500.00"),
                opened_at=date.today() - timedelta(days=idx * 10),
                closed_at=date.today() - timedelta(days=1) if statuses[idx] == "closed" else None,
            )
        )
    db.add_all(matters)
    db.flush()

    sessions = []
    for idx, matter in enumerate(matters[:6]):
        sessions.append(
            CourtSession(
                matter_id=matter.id,
                session_date=date.today() + timedelta(days=idx + 1),
                court_name=matter.court_name or "المحكمة الابتدائية بمسقط",
                hall_number=str(10 + idx),
                judge_name=f"القاضي التجريبي {idx + 1}",
                session_status="scheduled",
                next_action="تحضير مذكرة مختصرة قبل الجلسة.",
            )
        )
    sessions.append(
        CourtSession(
            matter_id=matters[6].id,
            session_date=date.today() - timedelta(days=4),
            court_name="المحكمة الابتدائية بمسقط",
            session_status="completed",
            decision_summary="تم تأجيل النطق بالحكم.",
            next_action="متابعة القرار القادم.",
        )
    )
    db.add_all(sessions)

    invoices = [
        Invoice(invoice_number="INV-2026-001", client_id=clients[0].id, matter_id=matters[0].id, issue_date=date.today(), due_date=date.today() + timedelta(days=15), subtotal=Decimal("5000"), discount=Decimal("0"), tax=Decimal("250"), total_amount=Decimal("5250"), paid_amount=Decimal("0"), status="unpaid", notes="أتعاب فتح ملف"),
        Invoice(invoice_number="INV-2026-002", client_id=clients[1].id, matter_id=matters[1].id, issue_date=date.today() - timedelta(days=7), due_date=date.today() + timedelta(days=7), subtotal=Decimal("12000"), discount=Decimal("500"), tax=Decimal("575"), total_amount=Decimal("12075"), paid_amount=Decimal("6000"), status="partially_paid"),
        Invoice(invoice_number="INV-2026-003", client_id=clients[2].id, matter_id=matters[2].id, issue_date=date.today() - timedelta(days=30), due_date=date.today() - timedelta(days=5), subtotal=Decimal("3000"), discount=Decimal("0"), tax=Decimal("150"), total_amount=Decimal("3150"), paid_amount=Decimal("3150"), status="paid"),
    ]
    db.add_all(invoices)
    db.flush()
    db.add(Payment(invoice_id=invoices[1].id, amount=Decimal("6000"), payment_date=date.today(), method="bank_transfer", reference_no="TRX-001"))
    db.add(Payment(invoice_id=invoices[2].id, amount=Decimal("3150"), payment_date=date.today() - timedelta(days=20), method="cash"))

    tasks = [
        Task(title="تحضير مذكرة دفاع", matter_id=matters[0].id, assigned_to_id=lawyer.id, created_by_id=admin.id, due_date=date.today(), priority="urgent", status="pending"),
        Task(title="الاتصال بالعميل لتحديث البيانات", client_id=clients[0].id, assigned_to_id=secretary.id, created_by_id=admin.id, due_date=date.today() + timedelta(days=1), priority="medium", status="in_progress"),
        Task(title="متابعة دفعة الفاتورة", client_id=clients[1].id, assigned_to_id=accountant.id, created_by_id=admin.id, due_date=date.today() - timedelta(days=2), priority="high", status="pending"),
        Task(title="أرشفة المستندات القديمة", matter_id=matters[6].id, assigned_to_id=secretary.id, created_by_id=admin.id, due_date=date.today() + timedelta(days=4), priority="low", status="pending"),
    ]
    db.add_all(tasks)

    db.add(
        Consultation(
            client_id=clients[3].id,
            requester_name="خالد عبدالله",
            requester_phone="0521234567",
            consultation_type="استشارة مدنية",
            subject="مراجعة عقد إيجار",
            description="طلب مراجعة بنود عقد إيجار تجاري.",
            status="assigned",
            assigned_lawyer_id=lawyer.id,
            consultation_date=date.today() + timedelta(days=3),
            fee_amount=Decimal("750"),
        )
    )

    settings = [
        OfficeSetting(key="office_name", value="مكتب سعيد الشبيبي للمحاماة", description="اسم المكتب"),
        OfficeSetting(key="phone", value="+968 0000 0000", description="رقم الهاتف"),
        OfficeSetting(key="email", value="info@saeed-law.om", description="البريد الإلكتروني"),
        OfficeSetting(key="address", value="مسقط، سلطنة عمان", description="العنوان"),
        OfficeSetting(key="invoice_footer", value="شكراً لثقتكم بمكتب سعيد الشبيبي للمحاماة.", description="نص أسفل الفاتورة"),
    ]
    db.add_all(settings)
    log_action(db, user=admin, action="seed_database", entity_type="system", new_value={"message": "initial seed"})
    db.commit()
    seed_accounting_defaults(db)
    seed_accounting_samples(db)
    seed_fixed_monthly_expenses(db)


def seed_accounting_samples(db: Session) -> None:
    if db.scalar(select(CaseFee).limit(1)):
        return
    matter = db.scalar(select(Matter).order_by(Matter.id))
    accountant = db.scalar(select(User).where(User.role == "accountant"))
    if not matter or not accountant:
        return
    has_demo_matter = db.scalar(select(Matter.id).where(Matter.title.ilike("قضية تجريبية%")).limit(1))
    if not has_demo_matter:
        return
    case_fee = CaseFee(
        matter_id=matter.id,
        client_id=matter.client_id,
        fee_amount=Decimal("10000"),
        payment_plan="installments",
        advance_payment=Decimal("2000"),
        monthly_installment=Decimal("1000"),
        due_date=date.today() + timedelta(days=30),
        paid_amount=Decimal("2000"),
        status="partial",
        notes="أتعاب تجريبية مرتبطة بالقضية.",
        is_cancelled=False,
    )
    db.add(case_fee)
    db.flush()
    db.add(
        Installment(
            client_id=matter.client_id,
            matter_id=matter.id,
            case_fee_id=case_fee.id,
            amount=Decimal("1000"),
            due_date=date.today() + timedelta(days=15),
            paid_amount=Decimal("0"),
            status="pending",
            notes="قسط تجريبي.",
        )
    )
    db.add(
        Expense(
            category="رسوم محاكم",
            amount=Decimal("350"),
            expense_date=date.today(),
            payment_method="cash",
            matter_id=matter.id,
            added_by_id=accountant.id,
            notes="مصروف تجريبي مرتبط بقضية.",
            status="active",
        )
    )
    db.commit()


def seed_fixed_monthly_expenses(db: Session) -> None:
    samples = [
        ("إيجار المكتب", "إيجار المكتب", Decimal("250"), 1, "bank_transfer", "مالك العقار"),
        ("الإنترنت والاتصالات", "الإنترنت والاتصالات", Decimal("30"), 5, "auto_debit", "مزود الاتصالات"),
        ("اشتراك نظام", "اشتراكات الأنظمة", Decimal("20"), 10, "card", "مزود النظام"),
        ("ضيافة وتنظيف", "تنظيف وضيافة", Decimal("40"), 25, "cash", "خدمات الضيافة والتنظيف"),
    ]
    changed = False
    for title, category, amount, due_day, payment_method, vendor_name in samples:
        if db.scalar(select(FixedMonthlyExpense).where(FixedMonthlyExpense.title == title)):
            continue
        db.add(
            FixedMonthlyExpense(
                title=title,
                category=category,
                amount=amount,
                due_day=due_day,
                payment_method=payment_method,
                vendor_name=vendor_name,
                is_active=True,
                notes="بيان تجريبي للمصاريف الشهرية الثابتة.",
            )
        )
        changed = True
    if changed:
        db.commit()

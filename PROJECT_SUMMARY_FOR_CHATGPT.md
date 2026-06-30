# ملخص مشروع نظام مكتب سعيد الشبيبي للمحاماة

هذا الملف ملخص جاهز لاستخدامه كمصدر مع ChatGPT أو أي مساعد آخر لفهم المشروع بسرعة.

## فكرة المشروع

النظام هو لوحة إدارة داخلية لمكتب محاماة واحد فقط باسم:

**مكتب سعيد الشبيبي للمحاماة**

النظام ليس SaaS، ولا يحتوي على تعدد مكاتب، ولا اشتراكات، ولا Super Admin لمنصة عامة. كل البيانات والواجهات مخصصة لمكتب سعيد الشبيبي فقط.

## الهدف

إدارة أعمال مكتب المحاماة من مكان واحد:

- العملاء
- القضايا
- الجلسات
- المهام
- المستندات
- الفواتير
- المدفوعات
- الاستشارات
- المستخدمون والصلاحيات
- التقارير
- الإعدادات
- سجل النشاط Audit Log

كما يحتوي المشروع على موقع عام للعملاء قابل للأرشفة لمحركات البحث ومحركات الذكاء الصناعي، يعرض خدمات المكتب ومقالات قانونية وأسئلة شائعة وصفحات تواصل وسياسات.

## التقنية المستخدمة

### Backend

- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL عبر `DATABASE_URL`
- SQLite محلياً عند عدم ضبط `DATABASE_URL`
- Session-based authentication
- Pydantic schemas

### Frontend

- HTML
- Jinja2 Templates
- CSS محلي في `app/static/app.css`
- Tailwind CDN موجود كدعم إضافي
- Vanilla JavaScript بسيط في `app/static/app.js`
- واجهة عربية RTL
- لا يوجد React
- لا يوجد Vite

### Deployment

المشروع مجهز للنشر على Render كخدمة Web Service واحدة.

Build Command:

```bash
pip install -r requirements.txt && alembic upgrade head
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## طريقة التشغيل محلياً

يوجد ملف تشغيل جاهز:

```bat
run.bat
```

عند تشغيله يقوم بـ:

1. إنشاء virtual environment إذا لم تكن موجودة.
2. تثبيت المتطلبات من `requirements.txt`.
3. تشغيل migrations.
4. تشغيل خادم FastAPI.
5. فتح المتصفح على صفحة تسجيل الدخول.

الرابط المحلي:

```text
http://127.0.0.1:8000/login
```

## بيانات الدخول التجريبية

```text
Password لجميع الحسابات: Admin12345

admin@saeed-law.test       role: admin
lawyer@saeed-law.test      role: lawyer
secretary@saeed-law.test   role: secretary
accountant@saeed-law.test  role: accountant
viewer@saeed-law.test      role: viewer
```

## هيكل المشروع

```text
app/
  main.py
  config.py
  database.py
  templating.py
  models/
    core.py
  routes/
    auth.py
    dashboard.py
    clients.py
    matters.py
    sessions.py
    tasks.py
    documents.py
    invoices.py
    payments.py
    consultations.py
    users.py
    reports.py
    settings.py
    helpers.py
  schemas/
    __init__.py
  services/
    auth.py
    audit.py
    labels.py
    security.py
    seed.py
  templates/
    base.html
    dashboard.html
    auth/
    clients/
    matters/
    sessions/
    tasks/
    documents/
    invoices/
    payments/
    consultations/
    users/
    reports/
    settings/
    partials/
  static/
    app.css
    app.js
    uploads/
alembic/
  env.py
  versions/
    0001_initial.py
scripts/
  open-browser.ps1
requirements.txt
render.yaml
.env.example
README.md
run.bat
```

## الجداول الأساسية

تم إنشاء النماذج الأساسية في:

```text
app/models/core.py
```

الجداول:

- User
- Client
- Matter
- CourtSession
- Task
- Document
- Invoice
- Payment
- Consultation
- OfficeSetting
- AuditLog

## الأدوار والصلاحيات

الأدوار:

- `admin`
- `lawyer`
- `secretary`
- `accountant`
- `viewer`

التحقق من تسجيل الدخول والصلاحيات موجود في:

```text
app/services/auth.py
```

القاعدة العامة:

- كل الصفحات محمية بتسجيل الدخول.
- المدير `admin` لديه صلاحية كاملة.
- `viewer` للمشاهدة فقط.
- العمليات الحساسة تعرض confirm dialog في الواجهة.
- العمليات المهمة تسجل في `AuditLog`.

تم فصل لوحة التحكم حسب الدور:

```text
app/templates/dashboard/admin.html
app/templates/dashboard/lawyer.html
app/templates/dashboard/secretary.html
app/templates/dashboard/accountant.html
app/templates/dashboard/viewer.html
```

المسار `/dashboard` يختار القالب والبيانات المناسبة حسب `user.role`.

القائمة الجانبية تختلف حسب الدور من خلال:

```text
app/services/permissions.py
```

## الصفحات المنفذة

## صفحات الموقع العام SEO/AEO

تمت إضافة موقع عام منفصل عن لوحة الإدارة:

- `/` الصفحة الرئيسية العامة.
- `/about` من نحن.
- `/services` الخدمات القانونية.
- `/services/{slug}` صفحة مستقلة لكل خدمة.
- `/legal-library` المكتبة القانونية.
- `/legal-library/{slug}` صفحة مستقلة لكل مقال.
- `/faq` الأسئلة الشائعة القانونية.
- `/contact` تواصل معنا.
- `/book-appointment` حجز موعد للعملاء.
- `/privacy-policy` سياسة الخصوصية.
- `/legal-disclaimer` إخلاء المسؤولية القانونية.
- `/sitemap.xml` خريطة الموقع.
- `/robots.txt` توجيهات محركات البحث.

ملفات الموقع العام:

```text
app/routes/public.py
app/services/public_content.py
app/templates/public/
app/static/app.css
```

الموقع العام يحتوي على:

- Meta titles و meta descriptions.
- Canonical URLs.
- Open Graph.
- Schema.org من نوع LegalService وFAQPage وArticle.
- محتوى سؤال وجواب مناسب لمحركات الذكاء الصناعي.
- صفحات خدمات قانونية مستقلة.
- مقالات قانونية بإجابة مباشرة في بداية المقال.

ملاحظة مهمة: بيانات الاتصال العامة موجودة في `app/services/public_content.py` ويجب استبدال رقم الهاتف وواتساب والبريد الإلكتروني بالقيم الرسمية للمكتب قبل النشر.

## نظام حجز المواعيد

تمت إضافة نظام حجز مواعيد عام للعملاء:

- صفحة الحجز: `/book-appointment`
- صفحة الإدارة الداخلية: `/appointments`
- المواعيد من 3:00 مساءً إلى 7:00 مساءً.
- مدة الموعد 30 دقيقة.
- آخر فترة متاحة تبدأ 6:30 مساءً.
- يمنع النظام حجز موعدين بنفس التاريخ والوقت من خلال تحقق برمجي وقيد فريد في قاعدة البيانات.
- حالة الحجز الافتراضية `pending`.
- يمكن للإدارة تغيير الحالة إلى `confirmed` أو `completed` أو `cancelled`.

الملفات:

```text
app/services/appointments.py
app/routes/appointments.py
app/templates/public/book_appointment.html
app/templates/appointments/index.html
alembic/versions/0002_appointments.py
```

## النظام المحاسبي

تمت إضافة نظام محاسبي داخلي لمكتب سعيد الشبيبي للمحاماة داخل المشروع الحالي.

المسار الرئيسي:

```text
/accounting
```

يشمل:

- لوحة تحكم مالية.
- إدارة العملاء مالياً.
- أتعاب القضايا.
- سندات القبض.
- سندات الصرف.
- المصروفات.
- الرواتب.
- الدفعات والأقساط.
- الحسابات البنكية والخزينة.
- القيود اليومية.
- دليل الحسابات.
- التقارير المالية.

الجداول الجديدة:

- CaseFee
- ReceiptVoucher
- PaymentVoucher
- Expense
- SalaryRecord
- Installment
- FinancialAccount
- AccountTransfer
- ChartAccount
- JournalEntry

الملفات:

```text
app/routes/accounting.py
app/services/accounting.py
app/templates/accounting/
alembic/versions/0003_accounting.py
```

الصلاحيات:

- المدير يرى القسم ويعتمد سندات الصرف التي تحتاج اعتماداً.
- المحاسب يضيف ويتابع العمليات المالية.
- العمليات الحساسة تسجل في AuditLog.
- لا يوجد حذف نهائي للعمليات المالية، بل إلغاء أو تغيير حالة مع سبب.
- أتعاب القضايا تدعم `الدفع عند الفوز` عبر `payment_plan=success_fee` و`status=contingent`. يتم تسجيل `success_percentage` كنسبة من مبلغ الفوز، ثم عند الفوز يدخل المستخدم `won_amount` ويحسب النظام `fee_amount = won_amount * success_percentage / 100` ويحولها إلى مستحق.

بيانات تجريبية محاسبية يتم إنشاؤها في `app/services/seed.py`.

### Authentication

- `/login`
- `/logout`
- `/forgot-password`

### Dashboard

- `/dashboard`

تعرض:

- عدد العملاء
- عدد القضايا المفتوحة
- جلسات الأسبوع
- المهام المتأخرة
- الفواتير غير المدفوعة
- المدفوعات هذا الشهر
- آخر العملاء
- آخر القضايا
- الجلسات القادمة
- مهام اليوم
- آخر الأنشطة

### Clients

- `/clients`
- `/clients/new`
- `/clients/{id}`
- `/clients/{id}/edit`

### Matters / Cases

- `/matters`
- `/matters/new`
- `/matters/{id}`
- `/matters/{id}/edit`

### Court Sessions

- `/sessions`
- `/sessions/new`
- `/sessions/{id}/edit`

### Tasks

- `/tasks`
- `/tasks/new`
- `/tasks/{id}/edit`

### Documents

- `/documents`

يدعم رفع المستندات وربطها بعميل أو قضية، مع خيار المستند السري.

### Invoices

- `/invoices`
- `/invoices/new`
- `/invoices/{id}`
- `/invoices/{id}/print`

### Payments

- `/payments`
- تسجيل دفعة من صفحة الفاتورة عبر `/invoices/{invoice_id}/payments`

### Consultations

- `/consultations`
- `/consultations/new`
- `/consultations/{id}`

### Users

- `/users`
- `/users/new`
- `/users/{id}/edit`

خاصة بدور `admin`.

### Reports

- `/reports`
- `/reports/export/{report_name}.csv`

تشمل تقارير:

- القضايا حسب الحالة
- الجلسات القادمة
- العملاء الجدد
- الفواتير غير المدفوعة
- الإيرادات الشهرية
- أداء المحامين
- تصدير CSV

### Settings

- `/settings`

خاصة بدور `admin`.

## ملفات مهمة

### تشغيل التطبيق

```text
app/main.py
```

يحتوي على إنشاء تطبيق FastAPI، ربط routers، تحميل static files، وتشغيل seed data عند بداية التشغيل.

### إعدادات البيئة

```text
app/config.py
```

يدعم:

- `APP_NAME`
- `SECRET_KEY`
- `DATABASE_URL`
- `UPLOAD_DIR`
- `SESSION_MAX_AGE`

### قاعدة البيانات

```text
app/database.py
```

يحتوي على:

- `engine`
- `SessionLocal`
- `Base`
- `get_db`

### بيانات Seed

```text
app/services/seed.py
```

ينشئ:

- مدير النظام
- مستخدمين تجريبيين
- عملاء تجريبيين
- قضايا تجريبية
- جلسات
- فواتير
- مدفوعات
- مهام
- استشارة
- إعدادات المكتب

### التصميم

```text
app/templates/base.html
app/static/app.css
app/static/app.js
```

التصميم عربي RTL، يحتوي على:

- Sidebar
- Topbar
- Cards
- Tables
- Filters
- Forms
- Badges
- Confirm dialogs
- صفحة فاتورة مناسبة للطباعة

## قاعدة البيانات محلياً

إذا لم يتم ضبط `DATABASE_URL`، يستخدم النظام:

```text
sqlite:///./saeed_law.db
```

ملف SQLite المحلي:

```text
saeed_law.db
```

وهو متجاهل في `.gitignore`.

## ملاحظات تطوير مهمة

- المشروع عملي وقابل للتشغيل، لكنه ليس بديلاً عن مراجعة أمنية نهائية قبل الإنتاج.
- رفع المستندات حالياً يتم داخل `app/static/uploads`.
- في Render، التخزين المحلي قد لا يكون دائماً، لذلك الأفضل لاحقاً ربط رفع الملفات بخدمة تخزين مثل S3 أو Cloudinary.
- صفحة `forgot-password` موجودة كمسار TODO ولم تنفذ استعادة كلمة المرور بالبريد.
- المصادقة حالياً Session-based وليست JWT.
- الواجهة تعتمد على Jinja2، لذلك لا تفتح ملفات HTML مباشرة من المجلد؛ يجب تشغيل FastAPI ثم فتح الرابط في المتصفح.

## أوامر مفيدة

تشغيل migrations:

```bash
python -m alembic upgrade head
```

تشغيل الخادم:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

فحص Python:

```bash
python -m compileall app
```

## طلب مناسب لاستخدامه مع ChatGPT

يمكن استخدام النص التالي:

```text
هذا ملخص مشروع نظام إدارة داخلي لمكتب محاماة مبني بـ FastAPI وJinja2 وSQLAlchemy. اقرأ ملف PROJECT_SUMMARY_FOR_CHATGPT.md وافهم هيكل المشروع والصفحات والجداول والصلاحيات، ثم ساعدني في تطوير أو تعديل ميزة محددة داخل هذا المشروع مع الحفاظ على نفس التقنية والأسلوب الحالي.
```

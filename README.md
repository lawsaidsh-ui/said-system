# نظام مكتب سعيد الشبيبي للمحاماة

نظام إدارة داخلي لمكتب محاماة واحد فقط، وليس SaaS. يدير العملاء، القضايا، الجلسات، المهام، المستندات، الفواتير، المدفوعات، الاستشارات، المستخدمين، التقارير، والإعدادات.

يتضمن المشروع أيضاً موقعاً عاماً للعملاء باسم مكتب سعيد الشبيبي للمحاماة، مخصصاً للظهور في Google ومحركات الذكاء الصناعي، ويحتوي على صفحات خدمات ومقالات وأسئلة شائعة وبيانات منظمة Schema.org.

## التقنية

- FastAPI و Jinja2 Templates
- SQLAlchemy و Alembic
- PostgreSQL عبر `DATABASE_URL`
- Session-based authentication
- واجهة عربية RTL باستخدام Tailwind CSS و CSS محلي

## التشغيل محلياً

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

إذا لم تضبط `DATABASE_URL` سيستخدم التطبيق SQLite محلياً في `saeed_law.db` لتسهيل التجربة.

## إعداد البيئة

انسخ `.env.example` إلى `.env` وعدل القيم:

```env
APP_NAME="مكتب سعيد الشبيبي للمحاماة"
SECRET_KEY="ضع-مفتاح-سري-قوي"
DATABASE_URL="postgresql+psycopg://user:password@host:5432/dbname"
UPLOAD_DIR="app/static/uploads"
SESSION_MAX_AGE=28800
```

## Migrations

```bash
alembic upgrade head
```

الهجرة الأولى تنشئ الجداول الأساسية المطلوبة. عند تشغيل التطبيق يتم أيضاً تنفيذ `create_all` كحماية للتشغيل المحلي، ثم تشغيل seed data إذا لم يكن المدير موجوداً.

## بيانات الدخول التجريبية

كلمة المرور لكل الحسابات التجريبية:

```text
Admin12345
```

الحسابات:

- `admin@saeed-law.test` مدير النظام.
- `lawyer@saeed-law.test` محام.
- `secretary@saeed-law.test` سكرتير.
- `accountant@saeed-law.test` محاسب.
- `data-entry@saeed-law.test` مدخل بيانات.
- `viewer@saeed-law.test` مشاهد.

كل دور ينتقل إلى لوحة تحكم مختلفة عند فتح `/dashboard`.

## النظام المحاسبي

تمت إضافة قسم محاسبي متكامل داخل النظام:

```text
/accounting
```

الصفحات:

- `/accounting` لوحة التحكم المالية.
- `/accounting/clients` إدارة العملاء مالياً.
- `/accounting/case-fees` أتعاب القضايا.
- `/accounting/receipts` سندات القبض.
- `/accounting/payment-vouchers` سندات الصرف.
- `/accounting/expenses` المصروفات.
- `/accounting/salaries` الرواتب.
- `/accounting/installments` الدفعات والأقساط.
- `/accounting/accounts` الحسابات البنكية والخزينة.
- `/accounting/journal` القيود اليومية.
- `/accounting/chart` دليل الحسابات.
- `/accounting/reports` التقارير المالية.

القسم متاح للمدير والمحاسب. لا يتم حذف العمليات المالية نهائياً؛ الإلغاء يتم بحالة وسبب إلغاء مع تسجيل في AuditLog للعمليات الحساسة.

يدعم أتعاب القضايا بنوع **الدفع عند الفوز**. في هذه الحالة تُسجل نسبة مئوية من مبلغ الفوز، ولا تدخل ضمن المستحقات حتى يتم إدخال مبلغ الفوز وتحويلها إلى مستحق. عندها يحسب النظام الأتعاب تلقائياً:

```text
الأتعاب = مبلغ الفوز × النسبة / 100
```

الجداول المحاسبية أضيفت في migration:

```text
alembic/versions/0003_accounting.py
```

الملفات الرئيسية:

```text
app/routes/accounting.py
app/services/accounting.py
app/templates/accounting/
```

## الصلاحيات

- `admin`: تحكم كامل، إدارة المستخدمين والإعدادات والتقارير.
- `lawyer`: إدارة القضايا والجلسات والمهام والمستندات المصرح بها.
- `secretary`: العملاء والجلسات والمواعيد والمستندات.
- `accountant`: الفواتير والمدفوعات والتقارير المالية والمهام.
- `data_entry`: إدخال وتحديث العملاء والقضايا والجلسات والمهام والمستندات والاستشارات وحجوزات العملاء.
- `viewer`: مشاهدة فقط.

لوحات التحكم المنفصلة موجودة في:

```text
app/templates/dashboard/admin.html
app/templates/dashboard/lawyer.html
app/templates/dashboard/secretary.html
app/templates/dashboard/accountant.html
app/templates/dashboard/viewer.html
```

روابط القائمة الجانبية حسب الدور معرفة في:

```text
app/services/permissions.py
```

## أهم الصفحات

- `/` الموقع العام
- `/about`
- `/services`
- `/services/{slug}`
- `/legal-library`
- `/legal-library/{slug}`
- `/faq`
- `/contact`
- `/book-appointment`
- `/privacy-policy`
- `/legal-disclaimer`
- `/sitemap.xml`
- `/robots.txt`
- `/login`
- `/dashboard`
- `/clients`
- `/matters`
- `/sessions`
- `/tasks`
- `/documents`
- `/invoices`
- `/consultations`
- `/users`
- `/reports`
- `/settings`

## صفحات الموقع العام

الموقع العام موجود في:

```text
app/routes/public.py
app/services/public_content.py
app/templates/public/
```

ويشمل:

- الصفحة الرئيسية العامة.
- صفحة من نحن.
- صفحة الخدمات القانونية.
- صفحة مستقلة لكل خدمة.
- المكتبة القانونية.
- صفحة مستقلة لكل مقال.
- الأسئلة الشائعة القانونية.
- تواصل معنا.
- سياسة الخصوصية.
- إخلاء المسؤولية القانونية.
- Sitemap و robots.txt.
- نظام حجز مواعيد للعملاء.

تنبيه: روابط التواصل الحالية في `app/services/public_content.py` موضوعة كقيم قابلة للتعديل، ويجب استبدال رقم الهاتف وواتساب والبريد بالقيم الرسمية للمكتب قبل النشر.

## نظام حجز المواعيد

تمت إضافة حجز مواعيد للعملاء عبر:

```text
/book-appointment
```

قواعد الحجز:

- المواعيد من الساعة 3:00 مساءً إلى 7:00 مساءً.
- مدة الموعد 30 دقيقة.
- آخر موعد يبدأ 6:30 مساءً وينتهي 7:00 مساءً.
- لا يمكن حجز موعدين بنفس التاريخ والوقت.
- يتم حفظ الحجز بحالة `pending` حتى يؤكده المكتب.

إدارة الحجوزات من لوحة الإدارة:

```text
/appointments
```

الملفات المرتبطة:

```text
app/models/core.py
app/services/appointments.py
app/routes/public.py
app/routes/appointments.py
app/templates/public/book_appointment.html
app/templates/appointments/index.html
alembic/versions/0002_appointments.py
```

## النشر على Render

المشروع يحتوي `render.yaml` لخدمة Web Service واحدة مع PostgreSQL من Render.

Build Command:

```bash
pip install -r requirements.txt && alembic upgrade head
```

Start Command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

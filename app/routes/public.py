import json
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.routes.helpers import none_if_empty, parse_date
from app.services.appointments import CASE_TYPES, LITIGATION_DEGREES, available_slots, create_appointment, parse_slot
from app.services.public_content import (
    ARTICLES,
    ARTICLES_BY_SLUG,
    BASE_KEYWORDS,
    CITY,
    CLIENT_CONTENT,
    CONTACT_EMAIL,
    GENERAL_FAQS,
    OFFICE_NAME,
    PHONE_DISPLAY,
    PHONE_TEL,
    SERVICE_AREA,
    SERVICES,
    SERVICES_BY_SLUG,
    WHATSAPP_PHONE,
    WHATSAPP_URL,
    ArticlePage,
    ServicePage,
)
from app.templating import templates

router = APIRouter(tags=["public"])


def absolute_url(request: Request, path: str = "") -> str:
    return str(request.base_url).rstrip("/") + path


def public_context(request: Request, *, title: str, description: str, path: str, keywords: str = BASE_KEYWORDS) -> dict:
    return {
        "request": request,
        "user": None,
        "office_name": OFFICE_NAME,
        "service_area": SERVICE_AREA,
        "city": CITY,
        "phone_display": PHONE_DISPLAY,
        "phone_tel": PHONE_TEL,
        "whatsapp_url": WHATSAPP_URL,
        "contact_email": CONTACT_EMAIL,
        "services": SERVICES,
        "articles": ARTICLES,
        "client_content": CLIENT_CONTENT,
        "meta_title": title,
        "meta_description": description,
        "meta_keywords": keywords,
        "canonical_url": absolute_url(request, path),
    }


def dumps_schema(data: dict | list[dict]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def legal_service_schema(request: Request, *, name: str, description: str, url_path: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "LegalService",
        "name": name,
        "description": description,
        "url": absolute_url(request, url_path),
        "areaServed": {"@type": "Country", "name": SERVICE_AREA},
        "address": {"@type": "PostalAddress", "addressLocality": CITY, "addressCountry": "OM"},
        "telephone": PHONE_TEL,
        "email": CONTACT_EMAIL,
        "priceRange": "$$",
    }


def faq_schema(faqs: list[tuple[str, str]]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}}
            for question, answer in faqs
        ],
    }


def article_schema(request: Request, article: ArticlePage) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.title,
        "description": article.meta_description,
        "author": {"@type": "Organization", "name": OFFICE_NAME},
        "publisher": {"@type": "Organization", "name": OFFICE_NAME},
        "inLanguage": "ar",
        "mainEntityOfPage": absolute_url(request, f"/blog/{article.slug}"),
    }


@router.get("/")
def home(request: Request):
    description = (
        "الموقع الرسمي لمكتب سعيد الشبيبي للمحاماة في سلطنة عمان. خدمات قانونية للأفراد والشركات "
        "في القضايا المدنية والتجارية والعمالية والأحوال الشخصية والعقود والاستشارات."
    )
    schema = [
        legal_service_schema(request, name=OFFICE_NAME, description=description, url_path="/"),
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": OFFICE_NAME,
            "url": absolute_url(request, "/"),
            "inLanguage": "ar",
        },
    ]
    return templates.TemplateResponse(
        "public/home.html",
        {
            **public_context(
                request,
                title=f"{OFFICE_NAME} | مكتب محاماة في سلطنة عمان",
                description=description,
                path="/",
            ),
            "schema_json": dumps_schema(schema),
        },
    )


@router.get("/about")
def about(request: Request):
    description = f"تعرف على {OFFICE_NAME}، مكتب محاماة يقدم خدمات قانونية للأفراد والشركات في سلطنة عمان بسرية ووضوح مهني."
    return templates.TemplateResponse(
        "public/about.html",
        {
            **public_context(request, title=f"من نحن | {OFFICE_NAME}", description=description, path="/about"),
            "schema_json": dumps_schema(legal_service_schema(request, name=OFFICE_NAME, description=description, url_path="/about")),
        },
    )


@router.get("/services")
def services_index(request: Request):
    description = "تعرف على الخدمات القانونية التي يقدمها مكتب سعيد الشبيبي للمحاماة في سلطنة عمان للأفراد والشركات."
    return templates.TemplateResponse(
        "public/services_index.html",
        {
            **public_context(request, title=f"الخدمات القانونية | {OFFICE_NAME}", description=description, path="/services"),
            "schema_json": dumps_schema(legal_service_schema(request, name=f"الخدمات القانونية - {OFFICE_NAME}", description=description, url_path="/services")),
        },
    )


@router.get("/services/{slug}")
def service_detail(request: Request, slug: str):
    service = SERVICES_BY_SLUG.get(slug)
    if not service:
        raise HTTPException(status_code=404, detail="الخدمة غير موجودة")
    path = f"/services/{service.slug}"
    schema = [
        legal_service_schema(request, name=f"{service.title} - {OFFICE_NAME}", description=service.summary, url_path=path),
        faq_schema(service.faqs),
    ]
    return templates.TemplateResponse(
        "public/service_detail.html",
        {
            **public_context(
                request,
                title=service.seo_title,
                description=service.meta_description,
                path=path,
                keywords=service.keywords,
            ),
            "service": service,
            "schema_json": dumps_schema(schema),
        },
    )


@router.get("/legal-library")
def legal_library_redirect():
    return RedirectResponse("/blog", status_code=301)


@router.get("/legal-library/{slug}")
def legal_library_article_redirect(slug: str):
    return RedirectResponse(f"/blog/{slug}", status_code=301)


@router.get("/blog")
def blog_index(request: Request):
    description = "مدونة قانونية مبسطة من مكتب سعيد الشبيبي للمحاماة تساعد العملاء على فهم موضوعات قانونية شائعة في سلطنة عمان."
    return templates.TemplateResponse(
        "public/articles_index.html",
        {
            **public_context(request, title=f"المدونة القانونية | {OFFICE_NAME}", description=description, path="/blog"),
            "schema_json": dumps_schema({"@context": "https://schema.org", "@type": "Blog", "name": "المدونة القانونية", "url": absolute_url(request, "/blog")}),
        },
    )


@router.get("/blog/{slug}")
def article_detail(request: Request, slug: str):
    article = ARTICLES_BY_SLUG.get(slug)
    if not article:
        raise HTTPException(status_code=404, detail="المقال غير موجود")
    path = f"/blog/{article.slug}"
    schema = [article_schema(request, article), faq_schema(article.faqs)]
    return templates.TemplateResponse(
        "public/article_detail.html",
        {
            **public_context(
                request,
                title=article.seo_title,
                description=article.meta_description,
                path=path,
                keywords=article.keywords,
            ),
            "article": article,
            "schema_json": dumps_schema(schema),
        },
    )


@router.get("/faq")
def faq(request: Request):
    description = "أسئلة شائعة قانونية للعملاء في سلطنة عمان حول الاستشارات والقضايا والعقود والتواصل مع مكتب محاماة."
    return templates.TemplateResponse(
        "public/faq.html",
        {
            **public_context(request, title=f"الأسئلة الشائعة القانونية | {OFFICE_NAME}", description=description, path="/faq"),
            "faqs": GENERAL_FAQS,
            "schema_json": dumps_schema(faq_schema(GENERAL_FAQS)),
        },
    )


@router.get("/contact")
def contact(request: Request):
    description = f"تواصل مع {OFFICE_NAME} لطلب استشارة قانونية في سلطنة عمان عبر الاتصال أو واتساب."
    return templates.TemplateResponse(
        "public/contact.html",
        {
            **public_context(request, title=f"تواصل معنا | {OFFICE_NAME}", description=description, path="/contact"),
            "schema_json": dumps_schema(legal_service_schema(request, name=OFFICE_NAME, description=description, url_path="/contact")),
        },
    )


@router.post("/contact")
def contact_submit(
    name: str = Form(...),
    phone: str = Form(...),
    request_type: str = Form(...),
    message: str = Form(...),
):
    whatsapp_message = "\n".join(
        [
            "السلام عليكم، أحتاج استشارة قانونية وأرغب في معرفة الخطوة المناسبة.",
            f"الاسم: {name}",
            f"رقم الهاتف: {phone}",
            f"نوع الطلب: {request_type}",
            f"وصف مختصر: {message}",
        ]
    )
    return RedirectResponse(f"https://wa.me/{WHATSAPP_PHONE}?text={quote(whatsapp_message)}", status_code=303)


@router.get("/book-appointment")
def book_appointment_page(request: Request, appointment_date: str | None = None, db: Session = Depends(get_db)):
    selected_date = parse_date(appointment_date) if appointment_date else date.today()
    description = (
        "احجز موعداً مع مكتب سعيد الشبيبي للمحاماة. المواعيد متاحة من الساعة الثالثة حتى السابعة، "
        "ومدة كل موعد 30 دقيقة."
    )
    return templates.TemplateResponse(
        "public/book_appointment.html",
        {
            **public_context(request, title=f"حجز موعد | {OFFICE_NAME}", description=description, path="/book-appointment"),
            "selected_date": selected_date,
            "today": date.today(),
            "available_slots": available_slots(db, selected_date),
            "case_types": CASE_TYPES,
            "litigation_degrees": LITIGATION_DEGREES,
            "error": None,
            "success": request.query_params.get("success") == "1",
        },
    )


@router.post("/book-appointment")
def book_appointment_submit(
    request: Request,
    client_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(""),
    appointment_date: str = Form(...),
    appointment_time: str = Form(...),
    topic: str = Form(""),
    case_type: str = Form(""),
    litigation_degree: str = Form(""),
    message: str = Form(""),
    db: Session = Depends(get_db),
):
    selected_date = parse_date(appointment_date)
    description = "احجز موعداً مع مكتب سعيد الشبيبي للمحاماة من الساعة الثالثة حتى السابعة، ومدة كل موعد 30 دقيقة."
    try:
        create_appointment(
            db,
            client_name=client_name,
            phone=phone,
            email=none_if_empty(email),
            appointment_date=selected_date,
            appointment_time=parse_slot(appointment_time),
            topic=none_if_empty(topic),
            case_type=none_if_empty(case_type),
            litigation_degree=none_if_empty(litigation_degree),
            message=none_if_empty(message),
        )
    except ValueError as exc:
        return templates.TemplateResponse(
            "public/book_appointment.html",
            {
                **public_context(request, title=f"حجز موعد | {OFFICE_NAME}", description=description, path="/book-appointment"),
                "selected_date": selected_date,
                "today": date.today(),
                "available_slots": available_slots(db, selected_date),
                "case_types": CASE_TYPES,
                "litigation_degrees": LITIGATION_DEGREES,
                "error": str(exc),
                "success": False,
                "form": {
                    "client_name": client_name,
                    "phone": phone,
                    "email": email,
                    "topic": topic,
                    "case_type": case_type,
                    "litigation_degree": litigation_degree,
                    "message": message,
                },
            },
            status_code=400,
        )
    return RedirectResponse("/book-appointment?success=1", status_code=303)


@router.get("/privacy-policy")
def privacy_policy(request: Request):
    description = f"سياسة الخصوصية الخاصة بموقع {OFFICE_NAME} وطريقة التعامل مع بيانات التواصل والمعلومات المرسلة عبر الموقع."
    return templates.TemplateResponse(
        "public/privacy.html",
        public_context(request, title=f"سياسة الخصوصية | {OFFICE_NAME}", description=description, path="/privacy-policy"),
    )


@router.get("/legal-disclaimer")
def legal_disclaimer(request: Request):
    description = "إخلاء المسؤولية القانونية: محتوى الموقع معلومات عامة ولا يغني عن استشارة قانونية متخصصة بناءً على وقائع كل حالة."
    return templates.TemplateResponse(
        "public/disclaimer.html",
        public_context(request, title=f"إخلاء المسؤولية القانونية | {OFFICE_NAME}", description=description, path="/legal-disclaimer"),
    )


@router.get("/robots.txt")
def robots_txt(request: Request):
    body = f"""User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /clients
Disallow: /matters
Disallow: /sessions
Disallow: /tasks
Disallow: /documents
Disallow: /invoices
Disallow: /payments
Disallow: /consultations
Disallow: /users
Disallow: /settings
Disallow: /login
Sitemap: {absolute_url(request, "/sitemap.xml")}
"""
    return Response(content=body, media_type="text/plain; charset=utf-8")


@router.get("/sitemap.xml")
def sitemap(request: Request):
    static_paths = ["/", "/about", "/services", "/blog", "/faq", "/contact", "/book-appointment", "/privacy-policy", "/legal-disclaimer"]
    urls = static_paths + [f"/services/{item.slug}" for item in SERVICES] + [f"/blog/{item.slug}" for item in ARTICLES]
    today = date.today().isoformat()
    items = "\n".join(
        f"""  <url>
    <loc>{absolute_url(request, path)}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{"weekly" if path in ["/", "/services", "/blog"] else "monthly"}</changefreq>
    <priority>{"1.0" if path == "/" else "0.8"}</priority>
  </url>"""
        for path in urls
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}
</urlset>
"""
    return Response(content=xml, media_type="application/xml; charset=utf-8")

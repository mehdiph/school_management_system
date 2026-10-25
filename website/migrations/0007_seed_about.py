"""
Seed the «درباره ما» page: its row (model defaults hold the texts), four
values and four highlights (general statements, bundled images through
``static_fallback``), and milestones and facts as *inactive* examples whose
placeholder years and numbers show the admin the format. Nothing that
would read as a fact about the school is published; people and photos
are left for the school to add. Only creates rows.
"""

from django.db import migrations

VALUES = [
    ("🛡️", "امنیت و آرامش", "محیطی که در آن هر کودک احساس امنیت می‌کند و بی‌ترس سؤال می‌پرسد."),
    ("🔍", "یادگیری با تجربه", "بچه‌ها با ساختن، آزمودن و گفت‌وگو یاد می‌گیرند، نه فقط با حفظ کردن."),
    ("🤝", "احترام به هر کودک", "هر کودک سرعت و استعداد خودش را دارد و ما به آن احترام می‌گذاریم."),
    ("🏡", "همراهی با خانواده", "خانواده‌ها در جریان مسیر فرزندشان هستند و صدایشان شنیده می‌شود."),
]

HIGHLIGHTS = [
    {
        "title": "در کلاس، خودشان پیش می‌روند",
        "text": "درس‌ها با ابزارهای آموزشی امروز و با مشارکت خود بچه‌ها پیش می‌رود؛ "
                "معلم راهنماست، نه فقط گوینده.",
        "image_alt": "کلاس هوشمند مدرسه",
        "static_fallback": "website/images/hooshmand.jpg",
    },
    {
        "title": "ربات می‌سازند و کد می‌نویسند",
        "text": "از سال‌های اول با منطق برنامه‌نویسی و ساخت ربات آشنا می‌شوند و حل مسئله را تمرین می‌کنند.",
        "image_alt": "کلاس رباتیک و برنامه‌نویسی",
        "static_fallback": "website/images/robotic.jpg",
    },
    {
        "title": "با رنگ و کاردستی ایده‌هایشان را می‌گویند",
        "text": "زنگ هنر جایی برای کشف رنگ‌ها، ساختن کاردستی و بیان آزادانه ایده‌هاست.",
        "image_alt": "دانش‌آموزان در حال نقاشی",
        "static_fallback": "website/images/painting.jpeg",
    },
    {
        "title": "با هم بازی و ورزش می‌کنند",
        "text": "تربیت بدنی و بازی‌های گروهی، روحیه تیمی و مهارت‌های حرکتی بچه‌ها را تقویت می‌کند.",
        "image_alt": "دانش‌آموزان در حال ورزش",
        "static_fallback": "website/images/exercise.jpeg",
    },
]

EXAMPLE_NOTE = "نمونه: سال و متن واقعی را بنویسید و «فعال» را بزنید."

MILESTONES = [
    ("۱۳۰۰", "تأسیس مدرسه"),
    ("۱۳۰۰", "افتتاح شعبه دوم"),
    ("۱۳۰۰", "راه‌اندازی کارگاه رباتیک"),
]

FACTS = ["سال تجربه", "دانش‌آموز", "معلم و همکار", "شعبه"]


def seed(apps, schema_editor):
    AboutPage = apps.get_model("website", "AboutPage")
    AboutValue = apps.get_model("website", "AboutValue")
    AboutHighlight = apps.get_model("website", "AboutHighlight")
    AboutMilestone = apps.get_model("website", "AboutMilestone")
    AboutFact = apps.get_model("website", "AboutFact")

    page, _ = AboutPage.objects.get_or_create(pk=1, defaults={"hero_image_alt": "پسربچه‌ای با کوله‌پشتی، آماده رفتن به مدرسه"})

    # Only seed empty lists, so re-running never duplicates content.
    if not page.belief_values.exists():
        AboutValue.objects.bulk_create(
            AboutValue(page=page, emoji=emoji, title=title, text=text, order=i)
            for i, (emoji, title, text) in enumerate(VALUES, start=1)
        )
    if not page.highlights.exists():
        AboutHighlight.objects.bulk_create(
            AboutHighlight(page=page, order=i, **item) for i, item in enumerate(HIGHLIGHTS, start=1)
        )
    if not page.milestones.exists():
        AboutMilestone.objects.bulk_create(
            AboutMilestone(page=page, year=year, title=title, text=EXAMPLE_NOTE, order=i, is_active=False)
            for i, (year, title) in enumerate(MILESTONES, start=1)
        )
    if not page.facts.exists():
        AboutFact.objects.bulk_create(
            AboutFact(page=page, value="—", label=label, order=i, is_active=False)
            for i, label in enumerate(FACTS, start=1)
        )


def unseed(apps, schema_editor):
    for name in ("AboutValue", "AboutHighlight", "AboutMilestone", "AboutFact", "AboutPage"):
        apps.get_model("website", name).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0006_about"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

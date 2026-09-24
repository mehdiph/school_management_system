"""
Seed the landing page with the content that used to be hardcoded in
``website/index.html`` and ``base.html``, so the page looks exactly the
same right after ``migrate``. Images are not copied into MEDIA_ROOT:
rows point at the original static files through ``static_fallback``.
"""

from django.db import migrations

NAV_ITEMS = ["تماس با ما", "کلاس ها", "معلمان", "درباره ما", "وبلاگ", "مقاله"]

FOOTER_LINKS = [
    ("اینستاگرام", "social"),
    ("تلگرام", "social"),
    ("آپارات", "social"),
    ("درباره ما", "page"),
    ("سوالات متداول", "page"),
    ("تماس با ما", "page"),
]

SLIDES = [
    {
        "badge_text": "توسعه خلاقیت و مهارت",
        "badge_emoji": "🤖",
        "title": "کلاس‌های رباتیک و کدنویسی نسل قلم",
        "description": "محیطی تعاملی و عملی برای آشنایی دانش‌آموزان با دنیای برنامه‌نویسی خلاق، "
                       "ساخت کیت‌های رباتیک و اینترنت اشیاء.",
        "button_text": "مشاهده شرایط و ثبت‌نام",
        "image_alt": "دانش‌آموزان در کلاس رباتیک",
        "overlay_color": "orange",
        "static_fallback": "website/images/robatic-slider.jpeg",
    },
    {
        "badge_text": "کارگاه هنر و رنگ",
        "badge_emoji": "🎨",
        "title": "پرورش خلاقیت در زنگ هنر و نقاشی",
        "description": "کشف استعدادهای هنری کودکان با استفاده از تکنیک‌های نوین تصویرسازی، "
                       "کاردستی‌های خلاقانه و بازی با رنگ‌ها.",
        "button_text": "گالری آثار دانش‌آموزان",
        "image_alt": "دانش‌آموزان در حال نقاشی",
        "overlay_color": "blue",
        "static_fallback": "website/images/painting.jpeg",
    },
    {
        "badge_text": "پویایی و تندرستی",
        "badge_emoji": "🏃‍♂️",
        "title": "تربیت بدنی و بازی‌های گروهی پویا",
        "description": "تقویت روحیه تیمی و مهارت‌های حرکتی پایه در سالن‌های ورزشی سرپوشیده "
                       "و مدرن مدرسه نسل قلم.",
        "button_text": "مشاهده امکانات ورزشی",
        "image_alt": "دانش‌آموزان در حال ورزش",
        "overlay_color": "teal",
        "static_fallback": "website/images/exercise.jpeg",
    },
]

FEATURES = [
    {
        "title": "رباتیک و برنامه نویسی",
        "description": "آموزش جذاب و کاربردی علوم کامپیوتر از سنین پایین برای تقویت تفکر منطقی "
                       "و حل مسئله در دانش‌آموزان",
        "image_alt": "کلاس رباتیک و برنامه‌نویسی",
        "static_fallback": "website/images/robotic.jpg",
    },
    {
        "title": "کلاس‌های هوشمند",
        "description": "تجهیزات مدرن و تکنولوژی‌های آموزشی روز برای یادگیری تعاملی و جذاب دروس مختلف",
        "image_alt": "کلاس هوشمند مدرسه",
        "static_fallback": "website/images/hooshmand.jpg",
    },
    {
        "title": "معلمان مجرب",
        "description": "کادر آموزشی متخصص و با سابقه که با عشق و حوصله، مسیر یادگیری را برای "
                       "کودکان هموار می‌کنند",
        "image_alt": "معلم در کلاس درس",
        "static_fallback": "website/images/teacher.jpg",
    },
]

LEARNING_POINTS = [
    ("👑", "برنامه های خلاقانه", "بازی های آموزشی و سرگرم کننده"),
    ("", "یادگیری آسان", "روش های نوین و جذاب تدریس"),
    ("", "یادگیری آسان", "روش های نوین و جذاب تدریس"),
    ("", "یادگیری آسان", "روش های نوین و جذاب تدریس"),
]

TEACHERS = [
    ("علی رضایی", "استاد ریاضی"),
    ("سعید محمدی", "استاد علوم"),
    ("ماریا کریمی", "استاد زبان"),
    ("ندا حسینی", "استاد هنر"),
]


def seed(apps, schema_editor):
    SiteSettings = apps.get_model("website", "SiteSettings")
    NavMenuItem = apps.get_model("website", "NavMenuItem")
    FooterLink = apps.get_model("website", "FooterLink")
    LandingPage = apps.get_model("website", "LandingPage")
    HeroSlide = apps.get_model("website", "HeroSlide")
    FeatureCard = apps.get_model("website", "FeatureCard")
    LearningPoint = apps.get_model("website", "LearningPoint")
    LandingTeacher = apps.get_model("website", "LandingTeacher")

    # Model defaults already hold the original texts.
    site, _ = SiteSettings.objects.get_or_create(pk=1, defaults={"meta_title": "مدرسه نسل قلم"})
    page, _ = LandingPage.objects.get_or_create(
        pk=1,
        defaults={
            "intro_image_alt": "دانش آموزان مدرسه",
            "learning_image_alt": "دانش آموز شاد",
        },
    )

    # Only seed empty lists, so re-running never duplicates content.
    if not site.nav_items.exists():
        NavMenuItem.objects.bulk_create(
            NavMenuItem(site=site, title=title, url="#", order=i)
            for i, title in enumerate(NAV_ITEMS, start=1)
        )
    if not site.footer_links.exists():
        FooterLink.objects.bulk_create(
            FooterLink(site=site, title=title, kind=kind, url="#", order=i)
            for i, (title, kind) in enumerate(FOOTER_LINKS, start=1)
        )
    if not page.slides.exists():
        HeroSlide.objects.bulk_create(
            HeroSlide(page=page, button_url="#", order=i, **data)
            for i, data in enumerate(SLIDES, start=1)
        )
    if not page.features.exists():
        FeatureCard.objects.bulk_create(
            FeatureCard(page=page, order=i, **data)
            for i, data in enumerate(FEATURES, start=1)
        )
    if not page.learning_points.exists():
        LearningPoint.objects.bulk_create(
            LearningPoint(page=page, icon_emoji=emoji, title=title, subtitle=subtitle, order=i)
            for i, (emoji, title, subtitle) in enumerate(LEARNING_POINTS, start=1)
        )
    if not page.teachers.exists():
        LandingTeacher.objects.bulk_create(
            LandingTeacher(page=page, name_override=name, specialty_override=specialty, order=i)
            for i, (name, specialty) in enumerate(TEACHERS, start=1)
        )


def unseed(apps, schema_editor):
    for name in (
        "NavMenuItem", "FooterLink", "HeroSlide", "FeatureCard",
        "LearningPoint", "LandingTeacher", "SiteSettings", "LandingPage",
    ):
        apps.get_model("website", name).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from website.images import METADATA_HELP, PUBLIC_PHOTO_HELP, reencode_new_photo
from website.validators import IMAGE_VALIDATORS, validate_link

from .base import OrderedItem, SingletonModel, image_url

INTRO_IMAGE_FALLBACK = "website/images/happy_young_boy.png"
LEARNING_IMAGE_FALLBACK = "website/images/giraffe.png"


def _image_field(upload_to, size_hint, verbose_name="تصویر"):
    return models.ImageField(
        upload_to=upload_to,
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name=verbose_name,
        help_text=f"ابعاد پیشنهادی {size_hint} پیکسل؛ jpg، png یا webp، حداکثر ۲ مگابایت.",
    )


def _alt_field():
    return models.CharField(
        max_length=150,
        blank=True,
        verbose_name="متن جایگزین تصویر (alt)",
        help_text="توضیح کوتاه تصویر برای نابینایان و موتورهای جستجو.",
    )


def _link_field(verbose_name, default="#"):
    return models.CharField(
        max_length=300,
        blank=True,
        default=default,
        validators=[validate_link],
        verbose_name=verbose_name,
    )


def _static_fallback_field():
    # Set only by the seed migration; see ``image_url``.
    return models.CharField(max_length=200, blank=True, editable=False)


class LandingPage(SingletonModel):
    """All single-value content of the landing page, one fieldset per section."""

    show_hero_slider = models.BooleanField(default=True, verbose_name="نمایش اسلایدر بالای صفحه")
    show_intro = models.BooleanField(default=True, verbose_name="نمایش سکشن معرفی")
    show_features = models.BooleanField(default=True, verbose_name="نمایش سکشن «چرا ما»")
    show_learning = models.BooleanField(default=True, verbose_name="نمایش سکشن یادگیری فعال")
    show_teachers = models.BooleanField(default=True, verbose_name="نمایش سکشن اساتید")

    # --- Intro ---
    intro_title = models.TextField(
        max_length=200,
        default="آینده‌ای درخشان برای\nفرزند شما در مدرسه نسل قلم",
        verbose_name="عنوان",
        help_text="با Enter می‌توانید عنوان را دو خطی کنید.",
    )
    intro_text = models.TextField(
        default="ما با ایجاد محیطی شاد، خلاق و امن، اشتیاق به یادگیری را در کودکان "
                "پرورش می‌دهیم تا با اعتماد به نفس برای چالش‌های فردا آماده شوند.",
        verbose_name="توضیح",
    )
    intro_image = _image_field("website/intro/", "۷۰۰×۷۰۰ (PNG با پس‌زمینه شفاف)")
    intro_image_alt = _alt_field()
    intro_primary_text = models.CharField(max_length=40, blank=True, default="ثبت نام کنید", verbose_name="متن دکمه اول")
    intro_primary_url = _link_field("لینک دکمه اول")
    intro_secondary_text = models.CharField(max_length=40, blank=True, default="بازدید از مدرسه", verbose_name="متن دکمه دوم")
    intro_secondary_url = _link_field("لینک دکمه دوم")

    # --- Why us ---
    features_title = models.CharField(max_length=150, default="چرا مدرسه نسل قلم؟", verbose_name="عنوان")
    features_subtitle = models.TextField(
        blank=True,
        default="ما با بهره‌گیری از جدیدترین متدهای آموزشی و محیطی پویا، "
                "استعدادهای نهفته کودکان را کشف و شکوفا می‌کنیم.",
        verbose_name="زیرعنوان",
    )

    # --- Active learning ---
    learning_title = models.CharField(
        max_length=150,
        default="یادگیری فعال، ارتباط با اعتماد به نفس",
        verbose_name="عنوان",
    )
    learning_subtitle = models.TextField(
        blank=True,
        default="ما به کودکان کمک می‌کنیم تا با روش‌های خلاقانه و تعاملی، "
                "مهارت‌های لازم برای آینده را کسب کنند.",
        verbose_name="زیرعنوان",
    )
    learning_image = _image_field("website/learning/", "۷۰۰×۶۴۰")
    learning_image_alt = _alt_field()

    # --- Teachers ---
    teachers_title = models.CharField(max_length=150, default="اساتید مجرب ما", verbose_name="عنوان")
    teachers_subtitle = models.TextField(
        blank=True,
        default="با اساتید متخصص و متعهد مدرسه پیشرو آشنا شوید",
        verbose_name="زیرعنوان",
    )
    teachers_link_text = models.CharField(
        max_length=40, blank=True, default="آشنایی با همه معلمان", verbose_name="متن لینک صفحه معلمان"
    )
    teachers_link_url = _link_field("لینک صفحه معلمان", default="/teachers/")

    class Meta:
        verbose_name = "مدیریت صفحه اصلی"
        verbose_name_plural = "مدیریت صفحه اصلی"

    def __str__(self):
        return "محتوای صفحه اصلی"

    @property
    def intro_image_url(self):
        return image_url(self.intro_image, INTRO_IMAGE_FALLBACK)

    @property
    def learning_image_url(self):
        return image_url(self.learning_image, LEARNING_IMAGE_FALLBACK)


class HeroSlide(OrderedItem):
    class Overlay(models.TextChoices):
        ORANGE = "orange", "نارنجی"
        BLUE = "blue", "آبی"
        TEAL = "teal", "سبزآبی"
        PURPLE = "purple", "بنفش"

    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="slides", verbose_name="صفحه اصلی")
    badge_text = models.CharField(max_length=60, blank=True, verbose_name="متن برچسب")
    badge_emoji = models.CharField(max_length=10, blank=True, verbose_name="ایموجی برچسب", help_text="مثال: 🎨")
    title = models.CharField(max_length=120, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیح")
    button_text = models.CharField(max_length=40, blank=True, verbose_name="متن دکمه")
    button_url = _link_field("لینک دکمه")
    image = _image_field("website/hero/", "۱۶۰۰×۶۰۰ (افقی؛ سوژه اصلی سمت چپ تصویر)", "تصویر پس‌زمینه")
    image_alt = _alt_field()
    overlay_color = models.CharField(
        max_length=10,
        choices=Overlay.choices,
        default=Overlay.ORANGE,
        verbose_name="رنگ لایه روی تصویر",
    )
    static_fallback = _static_fallback_field()

    class Meta(OrderedItem.Meta):
        verbose_name = "اسلاید"
        verbose_name_plural = "اسلایدهای بالای صفحه"

    def __str__(self):
        return self.title

    @property
    def image_url(self):
        return image_url(self.image, self.static_fallback)

    @property
    def alt_text(self):
        return self.image_alt or self.title


class FeatureCard(OrderedItem):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="features", verbose_name="صفحه اصلی")
    image = _image_field("website/features/", "۴۰۰×۴۰۰ (مربع)")
    image_alt = _alt_field()
    title = models.CharField(max_length=80, verbose_name="عنوان")
    description = models.TextField(blank=True, verbose_name="توضیح")
    static_fallback = _static_fallback_field()

    class Meta(OrderedItem.Meta):
        verbose_name = "کارت «چرا ما»"
        verbose_name_plural = "کارت‌های «چرا ما»"

    def __str__(self):
        return self.title

    @property
    def image_url(self):
        return image_url(self.image, self.static_fallback)

    @property
    def alt_text(self):
        return self.image_alt or self.title


class LearningPoint(OrderedItem):
    page = models.ForeignKey(
        LandingPage, on_delete=models.CASCADE, related_name="learning_points", verbose_name="صفحه اصلی"
    )
    icon_emoji = models.CharField(max_length=10, blank=True, verbose_name="ایموجی آیکون", help_text="مثال: 👑")
    icon_image = _image_field("website/learning/icons/", "۹۶×۹۶", "تصویر آیکون")
    title = models.CharField(max_length=80, verbose_name="عنوان")
    subtitle = models.CharField(max_length=150, blank=True, verbose_name="زیرعنوان")

    class Meta(OrderedItem.Meta):
        verbose_name = "آیتم یادگیری فعال"
        verbose_name_plural = "آیتم‌های یادگیری فعال"

    def __str__(self):
        return self.title

    @property
    def icon_url(self):
        return image_url(self.icon_image)


class LandingTeacher(OrderedItem):
    """
    A teacher on the public site: the landing page's row and the «معلمان»
    page share these rows; ``on_home`` and ``on_teachers_page`` say where
    each one appears, and nothing is shown unless ticked.

    Linked to a real ``TeacherProfile`` when possible, so the name follows
    the user's account (never the username) and the specialty the
    profile's ``field_of_study``; the ``*_override`` fields win whenever
    they are filled in. Nothing else is read from the account or profile:
    the photo is only the one uploaded here (ADR-025), and experience and
    education are typed on the card.
    """

    teacher = models.ForeignKey(
        "staff.TeacherProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="landing_cards",
        verbose_name="معلم",
        help_text="اختیاری. از حساب معلم فقط نام و نام خانوادگی و رشته تحصیلی خوانده می‌شود؛ "
                  "عکس و اطلاعات دیگر حساب هرگز نمایش داده نمی‌شود.",
    )
    name_override = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="نام نمایشی",
        help_text="اگر خالی باشد، نام و نام خانوادگی حساب معلم نمایش داده می‌شود.",
    )
    photo_override = models.ImageField(
        upload_to="website/teachers/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="عکس",
        help_text="ابعاد پیشنهادی ۶۰۰×۸۰۰ (عمودی)؛ jpg، png یا webp، حداکثر ۲ مگابایت. "
                  + PUBLIC_PHOTO_HELP + " " + METADATA_HELP + " بدون عکس، حرف اول نام نمایش داده می‌شود.",
    )
    specialty_override = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="عنوان تخصص",
        help_text="مثال: آموزگار پایه دوم، معلم زبان انگلیسی. اگر خالی باشد، رشته تحصیلی پروفایل معلم "
                  "نمایش داده می‌شود، که معمولاً رشته دانشگاهی است، نه درسی که تدریس می‌کند.",
    )
    group = models.ForeignKey(
        "website.TeacherGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
        verbose_name="گروه آموزشی",
        help_text="گروه‌ها در «صفحه معلمان» تعریف می‌شوند. معلمان گروه غیرفعال نمایش داده نمی‌شوند.",
    )
    on_teachers_page = models.BooleanField(
        default=False,
        verbose_name="نمایش در صفحه معلمان",
        help_text="فقط با رضایت خود معلم منتشر کنید.",
    )
    on_home = models.BooleanField(default=False, verbose_name="نمایش در صفحه اصلی")
    experience = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="سابقه تدریس",
        help_text="همان‌طور که نوشته شود نمایش داده می‌شود؛ مثال: ۱۲ سال. از اطلاعات پرسنلی خوانده نمی‌شود.",
    )
    education = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="تحصیلات",
        help_text="مثال: کارشناسی ارشد آموزش ابتدایی. از پروفایل معلم خوانده نمی‌شود.",
    )
    quote = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="سخن یا باور آموزشی",
        help_text="یک یا دو جمله از زبان خود معلم؛ با جوهر قرمز روی کاغذ دفتر نمایش داده می‌شود.",
    )
    bio = models.TextField(
        max_length=400,
        blank=True,
        verbose_name="معرفی کوتاه",
        help_text="حداکثر ۴۰۰ کاراکتر؛ با «درباره …» باز می‌شود.",
    )
    slug = models.SlugField(
        max_length=80,
        unique=True,
        blank=True,
        allow_unicode=True,
        verbose_name="نامک (برای لینک)",
        help_text="اگر خالی باشد، از نام ساخته می‌شود و بعد از آن با تغییر نام عوض نمی‌شود. "
                  "لینک مستقیم به این معلم: /teachers/#نامک",
    )

    class Meta(OrderedItem.Meta):
        verbose_name = "معلم سایت"
        verbose_name_plural = "معلمان سایت"

    def __str__(self):
        return self.display_name or "معلم"

    def clean(self):
        if not self.display_name:
            raise ValidationError("یک معلم دارای نام انتخاب کنید یا نام نمایشی را وارد کنید.")

    def save(self, *args, **kwargs):
        reencode_new_photo(self, "photo_override")
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.display_name, allow_unicode=True)[:70].strip("-") or "teacher"
        others = type(self).objects.exclude(pk=self.pk)
        slug, n = base, 2
        while others.filter(slug=slug).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

    @property
    def _account_name(self):
        # Never the username: it is an internal login, not a public name.
        if not self.teacher_id:
            return ""
        user = self.teacher.staff.user
        return f"{user.first_name} {user.last_name}".strip()

    @property
    def display_name(self):
        return self.name_override.strip() or self._account_name

    @property
    def photo_url(self):
        return image_url(self.photo_override)

    @property
    def initial(self):
        name = self.display_name
        return name[0] if name else "?"

    @property
    def display_specialty(self):
        if self.specialty_override:
            return self.specialty_override
        if self.teacher and self.teacher.field_of_study:
            return self.teacher.field_of_study
        return ""

    @property
    def has_details(self):
        return bool(self.bio.strip() or self.education.strip())

from django.core.exceptions import ValidationError
from django.db import models

from website.images import METADATA_HELP, PUBLIC_PHOTO_HELP, reencode_new_photo
from website.validators import IMAGE_VALIDATORS

from .base import OrderedItem, SingletonModel, image_url
from .landing import _alt_field, _image_field, _link_field, _static_fallback_field

HERO_IMAGE_FALLBACK = "website/images/happy_young_boy.png"


class AboutPage(SingletonModel):
    """Texts and section switches of the «درباره ما» page."""

    show_story = models.BooleanField(default=True, verbose_name="نمایش متن داستان ما")
    show_timeline = models.BooleanField(default=True, verbose_name="نمایش مسیر سال‌ها")
    show_quote = models.BooleanField(
        default=False,
        verbose_name="نمایش سخن مدیر",
        help_text="تا وقتی متن و نام مدیر تأیید نشده، خاموش بماند.",
    )
    show_values = models.BooleanField(default=True, verbose_name="نمایش سکشن باورها")
    show_highlights = models.BooleanField(default=True, verbose_name="نمایش سکشن «در نسل قلم، بچه‌ها…»")
    show_facts = models.BooleanField(default=True, verbose_name="نمایش سکشن اعداد")
    show_team = models.BooleanField(default=True, verbose_name="نمایش سکشن همکاران")
    show_gallery = models.BooleanField(default=True, verbose_name="نمایش گالری عکس")
    show_branches = models.BooleanField(default=True, verbose_name="نمایش سکشن شعبه‌ها")
    show_cta = models.BooleanField(default=True, verbose_name="نمایش دعوت پایانی")

    # --- Hero ---
    hero_title = models.TextField(
        max_length=200,
        default="مدرسه‌ای که بچه‌ها در آن با شوق یاد می‌گیرند و خانواده‌ها با خیال آسوده همراهشان هستند.",
        verbose_name="عنوان (داستان مدرسه در یک جمله)",
        help_text="با Enter می‌توانید عنوان را دو خطی کنید.",
    )
    hero_text = models.TextField(
        blank=True,
        default="نسل قلم برای کودکانی است که می‌پرسند، می‌سازند و می‌نویسند؛ "
                "و برای خانواده‌هایی که می‌خواهند فرزندشان در محیطی امن و گرم بزرگ شود.",
        verbose_name="توضیح",
    )
    hero_image = _image_field("website/about/", "۶۰۰×۸۰۰ (عمودی؛ در قاب طاق‌دار نمایش داده می‌شود)")
    hero_image_alt = _alt_field()
    hero_button_text = models.CharField(
        max_length=40, blank=True, default="هماهنگی بازدید از مدرسه", verbose_name="متن دکمه"
    )
    hero_button_url = _link_field("لینک دکمه", default="/contact/")

    # --- Story and timeline ---
    story_title = models.CharField(max_length=100, default="داستان ما", verbose_name="عنوان")
    story_text = models.TextField(
        blank=True,
        default="نسل قلم با یک باور ساده شروع شد: هر کودک، اگر دیده و شنیده شود، "
                "راه یادگیری خودش را پیدا می‌کند.\n\n"
                "امروز هم همین باور در کلاس‌هایمان جاری است؛ در معلمانی که برای تک‌تک بچه‌ها "
                "وقت می‌گذارند، در کارگاه‌هایی که دست و ذهن را با هم به کار می‌گیرند، "
                "و در ارتباط نزدیکی که با خانواده‌ها داریم.",
        verbose_name="متن داستان",
        help_text="داستان واقعی مدرسه. با یک خط خالی، پاراگراف تازه شروع می‌شود.",
    )
    timeline_title = models.CharField(
        max_length=100,
        default="مسیر ما در گذر سال‌ها",
        verbose_name="عنوان مسیر سال‌ها",
        help_text="برای صفحه‌خوان‌ها خوانده می‌شود و روی صفحه دیده نمی‌شود.",
    )

    # --- Director's words ---
    quote_text = models.TextField(
        blank=True,
        default="از روز اول می‌خواستیم مدرسه‌ای بسازیم که بچه‌ها صبح‌ها با اشتیاق به آن بیایند. "
                "هر تصمیمی که می‌گیریم با همین پرسش سنجیده می‌شود: آیا برای بچه‌ها خوب است؟",
        verbose_name="متن سخن",
    )
    quote_name = models.CharField(max_length=100, blank=True, verbose_name="نام گوینده")
    quote_role = models.CharField(max_length=80, blank=True, default="مدیر مدرسه", verbose_name="سمت گوینده")
    quote_photo = models.ImageField(
        upload_to="website/about/quote/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="عکس گوینده",
        help_text="ابعاد پیشنهادی ۳۰۰×۳۰۰ پیکسل؛ jpg، png یا webp، حداکثر ۲ مگابایت. " + PUBLIC_PHOTO_HELP,
    )
    quote_photo_alt = _alt_field()

    # --- Beliefs ---
    values_title = models.CharField(max_length=100, default="باورهای ما", verbose_name="عنوان سکشن")
    mission_title = models.CharField(max_length=80, blank=True, default="مأموریت ما", verbose_name="عنوان مأموریت")
    mission_text = models.TextField(
        blank=True,
        default="پرورش کودکانی کنجکاو، مهربان و توانا که با اعتماد به نفس می‌آموزند "
                "و آموخته‌هایشان را در زندگی به کار می‌گیرند.",
        verbose_name="متن مأموریت",
    )
    vision_title = models.CharField(max_length=80, blank=True, default="چشم‌انداز ما", verbose_name="عنوان چشم‌انداز")
    vision_text = models.TextField(
        blank=True,
        default="مدرسه‌ای که خانواده‌ها با اطمینان انتخابش کنند و بچه‌ها سال‌ها بعد، "
                "روزهایش را با لبخند به یاد بیاورند.",
        verbose_name="متن چشم‌انداز",
    )

    # --- What makes us different ---
    highlights_title = models.CharField(max_length=100, default="در نسل قلم، بچه‌ها…", verbose_name="عنوان سکشن")
    highlights_text = models.TextField(
        blank=True,
        default="آنچه یک روز مدرسه را برای بچه‌های ما متفاوت می‌کند.",
        verbose_name="توضیح سکشن",
    )

    # --- Facts, team, gallery ---
    facts_title = models.CharField(max_length=100, default="نسل قلم در چند عدد", verbose_name="عنوان سکشن اعداد")
    team_title = models.CharField(max_length=100, default="همکاران ما", verbose_name="عنوان سکشن همکاران")
    team_text = models.TextField(
        blank=True,
        default="با کسانی آشنا شوید که در مدرسه و دفتر آن پاسخگوی شما هستند.",
        verbose_name="توضیح سکشن همکاران",
    )
    gallery_title = models.CharField(max_length=100, default="گوشه‌ای از مدرسه", verbose_name="عنوان گالری")

    # --- Branches ---
    branches_title = models.CharField(max_length=100, default="شعبه‌های ما", verbose_name="عنوان سکشن شعبه‌ها")
    branches_text = models.TextField(
        blank=True,
        default="تلفن، ساعت کاری و مسیریابی هر شعبه در صفحه تماس با ما آمده است.",
        verbose_name="توضیح سکشن شعبه‌ها",
        help_text="شعبه‌ها همان شعبه‌های «صفحه تماس با ما» هستند و نشانی‌شان همان‌جا ویرایش می‌شود.",
    )
    branches_link_text = models.CharField(
        max_length=40, blank=True, default="مسیریابی و تلفن", verbose_name="متن لینک هر شعبه"
    )
    branches_link_url = _link_field("لینک هر شعبه", default="/contact/")

    # --- Closing call to action ---
    cta_title = models.CharField(max_length=120, default="از نزدیک با مدرسه آشنا شوید", verbose_name="عنوان")
    cta_text = models.TextField(
        blank=True,
        default="برای بازدید از مدرسه، گفت‌وگو درباره ثبت‌نام یا هر پرسش دیگری، با دفتر مدرسه در تماس باشید.",
        verbose_name="توضیح",
    )
    cta_primary_text = models.CharField(max_length=40, blank=True, default="تماس با مدرسه", verbose_name="متن دکمه اول")
    cta_primary_url = _link_field("لینک دکمه اول", default="/contact/")
    cta_secondary_text = models.CharField(
        max_length=40,
        blank=True,
        verbose_name="متن دکمه دوم",
        help_text="اختیاری، مثلاً «ثبت‌نام». بدون متن یا لینک نمایش داده نمی‌شود.",
    )
    cta_secondary_url = _link_field("لینک دکمه دوم", default="")

    meta_title = models.CharField(
        max_length=70,
        default="درباره ما",
        verbose_name="عنوان صفحه (meta title)",
        help_text="عنوان تب مرورگر؛ نام سایت پس از آن می‌آید.",
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="توضیح صفحه (meta description)",
        help_text="حداکثر ۱۶۰ کاراکتر؛ در نتایج جستجو زیر عنوان نمایش داده می‌شود.",
    )

    class Meta:
        verbose_name = "صفحه درباره ما"
        verbose_name_plural = "صفحه درباره ما"

    def __str__(self):
        return "محتوای صفحه درباره ما"

    @property
    def hero_image_url(self):
        return image_url(self.hero_image, HERO_IMAGE_FALLBACK)

    @property
    def quote_photo_url(self):
        return image_url(self.quote_photo)

    @property
    def has_cta_secondary(self):
        return bool(self.cta_secondary_text.strip() and self.cta_secondary_url.strip())


class AboutMilestone(OrderedItem):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="milestones", verbose_name="صفحه درباره ما")
    year = models.CharField(max_length=20, verbose_name="سال", help_text="همان‌طور که نوشته شود نمایش داده می‌شود؛ مثال: ۱۳۹۲")
    title = models.CharField(max_length=100, verbose_name="عنوان")
    text = models.TextField(blank=True, verbose_name="توضیح")

    class Meta(OrderedItem.Meta):
        verbose_name = "رویداد مسیر سال‌ها"
        verbose_name_plural = "مسیر سال‌ها (به ترتیب زمان)"

    def __str__(self):
        return f"{self.year}: {self.title}"


class AboutValue(OrderedItem):
    page = models.ForeignKey(
        AboutPage, on_delete=models.CASCADE, related_name="belief_values", verbose_name="صفحه درباره ما"
    )
    emoji = models.CharField(max_length=10, blank=True, verbose_name="ایموجی", help_text="اختیاری؛ مثال: 🤝")
    title = models.CharField(max_length=80, verbose_name="عنوان")
    text = models.CharField(max_length=200, blank=True, verbose_name="توضیح یک‌خطی")

    class Meta(OrderedItem.Meta):
        verbose_name = "ارزش"
        verbose_name_plural = "ارزش‌های ما"

    def __str__(self):
        return self.title


class AboutHighlight(OrderedItem):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="highlights", verbose_name="صفحه درباره ما")
    image = _image_field("website/about/highlights/", "۸۰۰×۶۰۰ (افقی)")
    image_alt = _alt_field()
    title = models.CharField(max_length=80, verbose_name="عنوان")
    text = models.TextField(blank=True, verbose_name="توضیح")
    static_fallback = _static_fallback_field()

    class Meta(OrderedItem.Meta):
        verbose_name = "ویژگی مدرسه"
        verbose_name_plural = "در نسل قلم، بچه‌ها…"

    def __str__(self):
        return self.title

    @property
    def image_url(self):
        return image_url(self.image, self.static_fallback)

    @property
    def alt_text(self):
        return self.image_alt or self.title


class AboutFact(OrderedItem):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="facts", verbose_name="صفحه درباره ما")
    value = models.CharField(
        max_length=20,
        verbose_name="عدد",
        help_text="همان‌طور که نوشته شود نمایش داده می‌شود؛ مثال: ۴۰۰+ یا ۱۲ سال. "
                  "این عدد از داده‌های سامانه محاسبه نمی‌شود.",
    )
    label = models.CharField(max_length=80, verbose_name="توضیح عدد", help_text="مثال: دانش‌آموز")

    class Meta(OrderedItem.Meta):
        verbose_name = "عدد"
        verbose_name_plural = "اعداد"

    def __str__(self):
        return f"{self.value} {self.label}"


class AboutPerson(OrderedItem):
    """
    A leader or office colleague. Linked to a ``Staff`` row when possible,
    so the name follows the user's account; the photo never does: only an
    image uploaded here, on purpose, is published.
    """

    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="people", verbose_name="صفحه درباره ما")
    staff = models.ForeignKey(
        "staff.Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="about_cards",
        verbose_name="پرسنل",
    )
    name_override = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="نام نمایشی",
        help_text="اگر خالی باشد، نام حساب کاربری پرسنل نمایش داده می‌شود.",
    )
    role = models.CharField(max_length=80, verbose_name="سمت", help_text="مثال: مدیر مدرسه، معاون آموزشی، مسئول دفتر")
    photo_override = models.ImageField(
        upload_to="website/about/people/",
        blank=True,
        validators=IMAGE_VALIDATORS,
        verbose_name="عکس",
        help_text="ابعاد پیشنهادی ۴۰۰×۴۰۰ (مربع). " + PUBLIC_PHOTO_HELP + " " + METADATA_HELP
                  + " بدون عکس، حرف اول نام نمایش داده می‌شود.",
    )
    bio = models.CharField(max_length=150, blank=True, verbose_name="توضیح کوتاه")

    class Meta(OrderedItem.Meta):
        verbose_name = "همکار"
        verbose_name_plural = "همکاران (مدیران و کارکنان دفتر)"

    def __str__(self):
        return self.display_name or "همکار"

    def clean(self):
        if not self.name_override.strip() and not self._account_name:
            raise ValidationError("یک پرسنل دارای نام انتخاب کنید یا نام نمایشی را وارد کنید.")

    def save(self, *args, **kwargs):
        reencode_new_photo(self, "photo_override")
        super().save(*args, **kwargs)

    @property
    def _account_name(self):
        # Never the username: it is an internal login, not a public name.
        if not self.staff_id:
            return ""
        user = self.staff.user
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


class AboutPhoto(OrderedItem):
    page = models.ForeignKey(AboutPage, on_delete=models.CASCADE, related_name="photos", verbose_name="صفحه درباره ما")
    image = models.ImageField(
        upload_to="website/about/gallery/",
        validators=IMAGE_VALIDATORS,
        verbose_name="تصویر",
        help_text="ابعاد پیشنهادی ۱۲۰۰×۹۰۰ پیکسل؛ jpg، png یا webp، حداکثر ۲ مگابایت. " + PUBLIC_PHOTO_HELP,
    )
    image_alt = _alt_field()
    caption = models.CharField(max_length=150, blank=True, verbose_name="زیرنویس")

    class Meta(OrderedItem.Meta):
        verbose_name = "عکس گالری"
        verbose_name_plural = "گالری عکس"

    def __str__(self):
        return self.caption or f"عکس {self.pk}"

    @property
    def image_url(self):
        return image_url(self.image)

    @property
    def alt_text(self):
        return self.image_alt or self.caption

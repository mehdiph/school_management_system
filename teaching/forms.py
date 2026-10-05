from django import forms
from django.db.models import Max
from django_jalali.admin.widgets import AdminjDateWidget
from .models import SchoolSession, SessionContent
from .services import slot_errors
from scheduling.models.bell import Bell
from scheduling.services import persian_digits
from school.models import ClassSubject

#: Fields whose change re-runs the slot rules (teaching.services) on edit.
SLOT_FIELDS = {"class_subject", "date", "bell", "status"}


def active_class_subjects(queryset=None):
    """
    Narrows ``queryset`` (default: every class subject) to the active
    class subjects of active classes -- what the session form may offer.
    """

    if queryset is None:
        queryset = ClassSubject.objects.all()

    return queryset.filter(
        is_active=True,
        school_class__is_active=True,
    )


class SchoolSessionForm(forms.ModelForm):
    """
    ``session_number`` is not a form field on purpose: it is assigned in
    ``SchoolSession.save()`` (see ``next_session_numbers`` for the value
    shown to the teacher before saving).

    The slot rules (``teaching.services.slot_errors``: not in the future,
    not on Friday, Thursday only for a compensatory session, not in a
    closed or already recorded slot, a held session only in a timetable
    slot) run on every new session, and on an edit that changes the
    class subject, date, bell or status. The «تعطیل» status is never
    offered: only the academic calendar sets it.
    """

    class Meta:
        model = SchoolSession
        fields = [
            "class_subject",
            "date",
            "bell",
            "status",
        ]

        labels = {
            "class_subject": "درس کلاس",
            "date": "تاریخ جلسه",
            "bell": "زنگ",
            "status": "وضعیت",
        }

        # Rendered under each field. Django links them to the input with
        # aria-describedby automatically ("<id>_helptext").
        help_texts = {
            "class_subject": "کلاس و درسی که این جلسه برای آن برگزار شد",
            "date": "روی کادر بزنید تا تقویم باز شود",
            "bell": "زنگی که این جلسه در آن برگزار شد",
            "status": "برگزار شده، کنسل شده یا جبرانی",
        }

        error_messages = {
            "class_subject": {
                "required": "درس کلاس را انتخاب کنید.",
                "invalid_choice": "درس کلاس انتخاب‌شده معتبر نیست؛ دوباره انتخاب کنید.",
            },
            "date": {
                "required": "تاریخ جلسه را وارد کنید.",
                "invalid": "تاریخ جلسه معتبر نیست؛ آن را از تقویم انتخاب کنید.",
            },
            "bell": {
                "required": "زنگ جلسه را انتخاب کنید.",
                "invalid_choice": "زنگ انتخاب‌شده معتبر نیست.",
            },
            "status": {
                "required": "وضعیت جلسه را انتخاب کنید.",
                "invalid_choice": "وضعیت انتخاب‌شده معتبر نیست.",
            },
        }

        widgets = {
            "class_subject": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "date": AdminjDateWidget(
                attrs={
                    "class": "form-control",
                    "autocomplete": "off",
                }
            ),
            "bell": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, class_subjects=None, today=None, **kwargs):
        """
        ``class_subjects`` limits the dropdown (and therefore what the
        form accepts) -- the views pass the current teacher's own class
        subjects. Without it every active class subject is offered.
        """

        super().__init__(*args, **kwargs)

        if class_subjects is None:
            class_subjects = active_class_subjects()

        self.fields["class_subject"].queryset = (
            class_subjects
            .select_related(
                # everything ClassSubject.__str__ touches, so rendering the
                # dropdown is a single query
                "school_class__grade",
                "school_class__branch",
                "subject",
                "teacher_assignment__teacher__staff__user",
            )
            .order_by(
                "school_class__branch__name",
                "school_class__grade__level",
                "school_class__section",
                "subject__name",
            )
        )

        self.fields["class_subject"].required = True
        self.fields["date"].required = True

        # A session recorded before sessions had a bell may be edited
        # without picking one (unless it is moved: see clean()).
        self.fields["bell"].required = not (self.instance.pk and self.instance.bell_id is None)
        self.fields["bell"].queryset = Bell.objects.filter(is_active=True).order_by("order")
        self.fields["bell"].empty_label = "انتخاب زنگ"
        self.fields["bell"].label_from_instance = lambda bell: persian_digits(
            f"{bell.title} ({bell.start_time:%H:%M}–{bell.end_time:%H:%M})"
        )
        self.fields["status"].choices = [
            choice for choice in self.fields["status"].choices
            if choice[0] != SchoolSession.Status.HOLIDAY
        ]
        self.today = today

    def clean(self):
        cleaned = super().clean()
        class_subject, date = cleaned.get("class_subject"), cleaned.get("date")
        if class_subject is None or date is None or "status" not in cleaned:
            return cleaned
        if self.instance.pk and not SLOT_FIELDS & set(self.changed_data):
            return cleaned  # only the content changed: the slot was accepted before

        for field, message in slot_errors(
            class_subject,
            date,
            cleaned.get("bell"),
            cleaned["status"],
            exclude_pk=self.instance.pk,
            today=self.today,
        ):
            self.add_error(field, message)
        return cleaned

    def next_session_numbers(self):
        """
        ``{class_subject_id: number}``: the number ``SchoolSession.save()``
        would give a new session of each class subject in the dropdown.
        One query, however many class subjects there are.
        """

        queryset = self.fields["class_subject"].queryset

        # holidays have no number: a class subject with only holidays
        # must not get a NULL "last number"
        last_numbers = dict(
            SchoolSession.objects.counted()
            .filter(class_subject__in=queryset.values("pk"))
            .values("class_subject")
            .annotate(last=Max("session_number"))
            .values_list("class_subject", "last")
        )

        return {
            pk: (last_numbers.get(pk) or 0) + 1
            for pk in queryset.values_list("pk", flat=True)
        }


class SessionContentForm(forms.ModelForm):
    class Meta:
        model = SessionContent
        # Display order: the optional fields (activity, notes) come last.
        fields = ['title', 'content', 'homework', 'activity', 'notes']

        labels = {
            'title': 'عنوان درس',
            'content': 'مطالب تدریس شده',
            'homework': 'تکالیف منزل',
            'activity': 'فعالیت‌های کلاسی',
            'notes': 'نکات و عملکرد دانش‌آموزان',
        }

        help_texts = {
            'title': 'عنوان کوتاه درس یا موضوع این جلسه',
            'content': 'مطالب و مفاهیمی که در این جلسه تدریس کردید',
            'homework': 'اگر تکلیفی ندادید، بنویسید «ندارد»',
            'activity': 'فعالیت‌ها و تمرین‌هایی که در کلاس انجام شد',
            'notes': 'نکات، مشکلات یا عملکرد کلی دانش‌آموزان',
        }

        error_messages = {
            'title': {
                'required': 'عنوان درس را وارد کنید.',
                'max_length': 'عنوان درس نباید بیشتر از ۲۵۵ حرف باشد.',
            },
            'content': {
                'required': 'مطالب تدریس شده را بنویسید.',
            },
            'homework': {
                'required': 'تکالیف منزل را بنویسید؛ اگر تکلیفی ندادید، بنویسید «ندارد».',
            },
        }

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: جمع اعداد چند رقمی',
                'autocomplete': 'off',
                'enterkeyhint': 'next',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'مطالب و مفاهیم تدریس شده در این جلسه را بنویسید...'
            }),
            'homework': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'تکالیف منزل دانش‌آموزان...'
            }),
            'activity': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'فعالیت‌ها و تمرین‌های انجام شده در کلاس...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'نکات، مشکلات، یا عملکرد کلی دانش‌آموزان...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(SessionContentForm, self).__init__(*args, **kwargs)
        # تنظیم فیلدهای الزامی و اختیاری
        self.fields['title'].required = True
        self.fields['activity'].required = False
        self.fields['notes'].required = False

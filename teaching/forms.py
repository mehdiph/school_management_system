from django import forms
from django.db.models import Max
from django_jalali.admin.widgets import AdminjDateWidget
from .models import SchoolSession, SessionContent
from school.models import ClassSubject


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
    """

    class Meta:
        model = SchoolSession
        fields = [
            "class_subject",
            "date",
            "status",
        ]

        labels = {
            "class_subject": "درس کلاس",
            "date": "تاریخ جلسه",
            "status": "وضعیت",
        }

        # Rendered under each field. Django links them to the input with
        # aria-describedby automatically ("<id>_helptext").
        help_texts = {
            "class_subject": "کلاس و درسی که این جلسه برای آن برگزار شد",
            "date": "روی کادر بزنید تا تقویم باز شود",
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
            "status": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, class_subjects=None, **kwargs):
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

    def next_session_numbers(self):
        """
        ``{class_subject_id: number}``: the number ``SchoolSession.save()``
        would give a new session of each class subject in the dropdown.
        One query, however many class subjects there are.
        """

        queryset = self.fields["class_subject"].queryset

        last_numbers = dict(
            SchoolSession.objects
            .filter(class_subject__in=queryset.values("pk"))
            .values("class_subject")
            .annotate(last=Max("session_number"))
            .values_list("class_subject", "last")
        )

        return {
            pk: last_numbers.get(pk, 0) + 1
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

from django import forms
from django_jalali.forms import jDateField
from django_jalali.admin.widgets import AdminjDateWidget
from .models import SchoolSession, SessionContent
from school.models import ClassSubject


class SchoolSessionForm(forms.ModelForm):
    class Meta:
        model = SchoolSession
        fields = ['class_subject', 'date', 'session_number', 'status']

        labels = {
            'class_subject': 'درس کلاس',
            'date': 'تاریخ جلسه',
            'session_number': 'شماره جلسه',
            'status': 'وضعیت'
        }

        widgets = {
            'class_subject': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'session_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'required': True
            }),
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(SchoolSessionForm, self).__init__(*args, **kwargs)
        # فیلتر کردن فقط کلاس‌های فعال
        self.fields['class_subject'].queryset = ClassSubject.objects.filter(
            is_active=True,
            school_class__is_active=True
        ).select_related('school_class', 'subject', 'teacher')
        
        # تنظیم فیلدهای الزامی
        self.fields['class_subject'].required = True
        self.fields['date'].required = True
        self.fields['session_number'].required = True


class SessionContentForm(forms.ModelForm):
    class Meta:
        model = SessionContent
        fields = ['title', 'content', 'activity', 'homework', 'notes']

        labels = {
            'title': 'عنوان درس',
            'content': 'مطالب تدریس شده',
            'activity': 'فعالیت‌های کلاسی',
            'homework': 'تکالیف منزل',
            'notes': 'نکات و عملکرد دانش‌آموزان'
        }

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: جمع اعداد چند رقمی',
                'required': True
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'مطالب و مفاهیم تدریس شده در این جلسه را بنویسید...'
            }),
            'date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True
            }),
            'activity': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'فعالیت‌ها و تمرین‌های انجام شده در کلاس...'
            }),
            'homework': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'تکالیف منزل دانش‌آموزان...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'نکات، مشکلات، یا عملکرد کلی دانش‌آموزان...'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(SessionContentForm, self).__init__(*args, **kwargs)
        # تنظیم فیلدهای الزامی
        self.fields['title'].required = True

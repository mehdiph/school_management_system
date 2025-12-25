from django import forms
from .models import *


class SchoolSessionForm(forms.ModelForm):
    class Meta:
        model = SchoolSession
        fields = '__all__'
        exclude = ['created_at', 'school_class', 'session_number']

        labels = {
            'date': 'تاریخ جلسه',
            'status': 'وضعیت'
        }

class SessionContentForm(forms.ModelForm):
    class Meta:
        model = SessionContent
        fields = '__all__'
        exclude = ['session', 'created_at']

        labels = {
            'title': 'عنوان',
            'content': 'مطالب تدریس شده',
            'activity': 'فعالیت های کلاسی',
            'homework': 'تکالیف منزل',
            'notes': 'نکات و عملکرد دانش آموزان'
        }



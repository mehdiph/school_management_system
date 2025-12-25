from django import forms
from django_jalali.forms import jDateField, jDateTimeField
from django_jalali.admin.widgets import AdminjDateWidget, AdminSplitjDateTime
from .models import SchoolClass, AcademicYear, Grade


class SchoolClassForm(forms.ModelForm):
    class Meta:
        model = SchoolClass
        fields = ['year', 'grade', 'section', 'is_active']

        labels = {
            'year': 'سال تحصیلی',
            'grade': 'پایه',
            'section': 'نام کلاس',
            'is_active': 'فعال',
        }

        widgets = {
            'year': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'grade': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'section': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: الف، ب، ج یا 1، 2، 3',
                'maxlength': '255',
                'required': True
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super(SchoolClassForm, self).__init__(*args, **kwargs)
        self.fields['year'].queryset = AcademicYear.objects.filter(is_active=True)
        self.fields['grade'].queryset = Grade.objects.filter(is_active=True)
        
        # Make fields required
        self.fields['year'].required = True
        self.fields['grade'].required = True
        self.fields['section'].required = True
